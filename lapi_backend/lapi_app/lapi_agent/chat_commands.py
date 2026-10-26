"""Chat slash commands for agentic chat (WS5, WS11).

/skill                 list available skills
/skill <name> <ask>    run the request with that skill loaded
/instructions          show the dataset instructions
/instructions <change> draft new instructions (shown as a before/after card)
/optimize [focus]      review this dataset and draft better instructions

Commands only shape the request; proposals still need the user to press Save.
"""
import re
from .. import prompt_layers


def expand(tools, text):
    match = re.match(r'^\s*/(skill|instructions|optimize)\b\s*(.*)$', text, re.I | re.S)
    if not match: return None
    command, rest = match[1].lower(), match[2].strip()
    body = tools.body
    if command == 'skill':
        skills = tools.skills.index(tools.owner, body.dataset_id) if tools.skills else []
        if not rest:
            if not skills: return {'answer': 'No skills are available yet. Add one on the Skills page.'}
            return {'answer': 'Available skills:\n' + '\n'.join(f"- **{s['name']}**: {s['description']}" for s in skills) +
                              '\n\nType `/skill <name> <your request>` to use one.'}
        name, _, ask = rest.partition(' ')
        if not any(s['name'] == name.lower() for s in skills):
            return {'answer': f'There is no skill named "{name}". Type /skill to see the list.'}
        return {'text': f'Call load_skill with name "{name.lower()}" first, then follow it for this request: {ask or "apply the skill to the selected scope"}'}
    if not body.dataset_id:
        return {'answer': 'Select a dataset first; instructions belong to one dataset.'}
    current = prompt_layers.dataset_instructions(body.dataset_id)
    if command == 'instructions' and not rest:
        if not current['text']:
            return {'answer': 'This dataset has no instructions yet. Type `/instructions <what you want>` to draft some, or `/optimize` to let me suggest them.'}
        return {'answer': f"Dataset instructions (version {current['version']}):\n\n{current['text']}"}
    if command == 'instructions':
        return {'text': 'The user wants to change this dataset\'s instructions: "' + rest + '". Current instructions: """' +
                        (current['text'] or '(none)') + '""". Write the complete new instructions (under 4 KB, markdown) and call propose_instruction_update. Do not answer anything else.'}
    return {'text': 'Review this dataset to suggest better dataset instructions' + (f' focused on: {rest}' if rest else '') +
                    '. Use describe_results, list_documents and a search or two to learn what the data contains and which questions it answers. '
                    'Then write short, specific instructions (terminology, which fields matter, preferred answer format) and call propose_instruction_update. '
                    'Current instructions: """' + (current['text'] or '(none)') + '"""'}
