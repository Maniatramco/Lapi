"""Run the agentic chat evaluation set against a live Lapi workspace.

    LAPI_URL=http://<host> LAPI_USERNAME=<you> python lapi_testing/eval/run_chat_eval.py \
        --dataset "<dataset name>" --model "<chat model name>" [--only documents,results] [--out report.json]

The password is read from LAPI_PASSWORD or prompted (never passed on the command
line). Each question becomes a real chat turn in a new conversation, so it uses
your model quota; Gemini free-tier daily limits apply. The report lists pass/fail
per expectation, model calls, tools used, tokens and latency.
"""
import argparse
import getpass
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


class Client:
    def __init__(self, base):
        self.base = base.rstrip('/'); self.csrf = ''
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, path, method='GET', body=None, timeout=660):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + '/api' + path, data=data, method=method,
                                         headers={'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf})
        with self.opener.open(request, timeout=timeout) as response:
            return json.loads(response.read() or b'null')

    def login(self, username, password):
        self.csrf = self.call('/auth/login', 'POST', {'username': username, 'password': password})['csrf_token']


def ask(client, dataset, model, text, conversation_id=''):
    started = time.monotonic()
    plan = client.call('/agent-v2/plans', 'POST', {'text': text, 'planner_model_id': model['id'], 'dataset_id': dataset['id'],
                                                    'conversation_id': conversation_id, 'allow_external': True})
    conversation = client.call('/conversations/' + plan['conversation_id'])
    message = conversation['messages'][-1]
    return plan, message, round(time.monotonic() - started, 2)


def check(expect, plan, message, jobs_before, jobs_after):
    text = message.get('text') or ''
    tools = [t['tool'] for t in message.get('tool_trace', [])]
    results = {}
    if expect.get('must_cite'): results['cites_sources'] = bool(re.search(r'\[\d+\]', text)) and bool(message.get('citations'))
    if expect.get('tools_any'): results['used_expected_tool'] = bool(set(tools) & set(expect['tools_any'])) or (message.get('request_route', {}).get('validation', {}).get('result') == 'catalog')
    if expect.get('min_tools'): results['enough_tools'] = len(tools) >= expect['min_tools']
    if expect.get('must_not_invent'):
        results['admits_missing'] = bool(re.search(r"couldn'?t find|could not find|not (?:found|in|mentioned|stated)|no (?:evidence|information|mention)|don'?t (?:have|see)|isn'?t (?:in|mentioned)", text, re.I))
    if expect.get('phase_in'): results['phase'] = plan.get('phase') in expect['phase_in']
    if expect.get('phase_not'): results['phase'] = plan.get('phase') != expect['phase_not']
    if expect.get('no_mutation'): results['nothing_ran'] = jobs_before == jobs_after
    if expect.get('uses_history'): results['agentic_runtime'] = message.get('runtime') == 'agentic'
    validation = message.get('request_route', {}).get('validation', {})
    return results, {'tools': tools, 'model_calls': plan.get('model_calls'), 'validation': validation.get('result'),
                     'removed_sentences': validation.get('removed_sentences', 0), 'tokens': message.get('token_usage', {}).get('total_tokens'),
                     'citations': len(message.get('citations', [])), 'answer': text[:400]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', required=True); parser.add_argument('--model', required=True)
    parser.add_argument('--only', default=''); parser.add_argument('--out', default='chat_eval_report.json')
    parser.add_argument('--pause', type=float, default=4.0, help='seconds between questions (free-tier rate limits)')
    args = parser.parse_args()
    client = Client(os.environ.get('LAPI_URL', 'http://localhost'))
    client.login(os.environ['LAPI_USERNAME'], os.environ.get('LAPI_PASSWORD') or getpass.getpass('Lapi password: '))
    dataset = next(d for d in client.call('/datasets') if d['name'] == args.dataset)
    model = next(m for m in dataset.get('models', []) if m['name'] == args.model)
    documents = [d for d in client.call('/documents?dataset_id=' + dataset['id']) if d.get('status') == 'ready']
    document = documents[0]['name'] if documents else 'the first document'
    spec = json.loads((HERE / 'agentic_chat_eval.json').read_text())
    only = {c for c in args.only.split(',') if c}
    report = []
    for item in spec['questions']:
        if only and item['category'] not in only: continue
        turns = item.get('turns') or [item['question']]
        jobs_before = len(client.call('/jobs'))
        conversation = ''; latency = 0
        try:
            for turn in turns:
                plan, message, seconds = ask(client, dataset, model, turn.replace('{document}', document), conversation)
                conversation = plan['conversation_id']; latency += seconds
                time.sleep(args.pause)
            results, details = check(item['expect'], plan, message, jobs_before, len(client.call('/jobs')))
        except Exception as exc:  # report and continue; one failure must not stop the run
            results, details = {'completed': False}, {'error': str(exc)[:300]}
        passed = all(results.values()) if results else True
        report.append({'id': item['id'], 'category': item['category'], 'passed': passed, 'checks': results, 'latency_s': latency, **details})
        print(f"{'PASS' if passed else 'FAIL'} {item['id']:<14} {latency:>6}s {details.get('model_calls', '-')} calls  {item.get('question') or ' → '.join(turns)}")
    summary = {'passed': sum(r['passed'] for r in report), 'total': len(report),
               'by_category': {c: f"{sum(r['passed'] for r in report if r['category'] == c)}/{sum(1 for r in report if r['category'] == c)}"
                               for c in dict.fromkeys(r['category'] for r in report)}}
    Path(args.out).write_text(json.dumps({'summary': summary, 'results': report}, indent=1))
    print(json.dumps(summary, indent=1))
    return 0 if summary['passed'] == summary['total'] else 1


if __name__ == '__main__':
    sys.exit(main())
