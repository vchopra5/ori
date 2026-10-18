"""Keep reconstruction commentary out of learner instructions and visual evidence."""


def lesson_action(command):
    action = dict(command)
    name = str(action.get('name', ''))
    if name.lower().startswith('oh no, the ear points inward'):
        action['name'] = 'Fold the right ear'
    elif name.lower().startswith('rehearsal: fold the right ear'):
        action['name'] = 'Fold the right ear'
    return action
