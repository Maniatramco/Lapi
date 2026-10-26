"""Chat slash commands for agentic chat (WS5, WS11).

/skill                 list available skills
/skill <name> <ask>    run the request with that skill loaded
/instructions          show the dataset instructions
/instructions <change> draft new instructions (shown as a before/after card)
/optimize [focus]      review this dataset and draft better instructions

Commands only shape the request and preload read tools. The answer still comes
from the model after hybrid retrieval and passes the citation check; proposals
need the user to press Save.
"""
import re


def expand(tools, text):
    match = re.match(r'^\s*/(skill|instructions|optimize)\b\s*(.*)$', text, re.I | re.S)
    if not match: return None
    command, rest = match[1].lower(), match[2].strip()
    if command == 'skill':
        if not rest:
            return {'text': 'List the skills I can use, with one line on what each is for, and explain how to run one with /skill <name> <request>.',
                    'reads': [('list_skills', {})]}
        name, _, ask = rest.partition(' ')
        return {'text': f'Call load_skill with name "{name.lower()}" first (if it does not exist, say so and list the skills), '
                        f'then follow it for this request: {ask or "apply the skill to the selected scope"}',
                'reads': [('list_skills', {})]}
    if not tools.body.dataset_id:
        return {'text': 'The user typed /' + command + ' but no dataset is selected. Explain that instructions belong to one dataset and ask them to select one.',
                'reads': []}
    if command == 'instructions' and not rest:
        return {'text': "Show this dataset's current answer instructions and their version, or say there are none and how to add them (/instructions <change> or /optimize).",
                'reads': [('read_dataset_instructions', {})]}
    if command == 'instructions':
        return {'text': 'The user wants to change this dataset\'s instructions: "' + rest + '". Read the current instructions, write the complete new '
                        'instructions (under 4 KB, markdown) and call propose_instruction_update. Do not answer anything else.',
                'reads': [('read_dataset_instructions', {})]}
    return {'text': 'Review this dataset to suggest better dataset instructions' + (f' focused on: {rest}' if rest else '') +
                    '. Use describe_results, list_documents and a search or two to learn what the data contains and which questions it answers. '
                    'Then write short, specific instructions (terminology, which fields matter, preferred answer format) and call propose_instruction_update.',
            'reads': [('read_dataset_instructions', {}), ('describe_results', {})]}
