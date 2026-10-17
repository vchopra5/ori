"""Deterministic dialogue compaction; authoritative physics is always lossless."""
import hashlib
import json

DEFAULT_POLICY = dict(version=1, recent_exchanges=8, recent_chars=24000,
                      failure_entries=24, failure_chars=12000)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def physics_checkpoint(harness):
    physics = dict(state=harness.state(), layers=harness.layer_state(),
                   metrics=harness.metrics(), accepted_commands=harness.history)
    return dict(version=1, physics=physics, sha256=digest(physics))


def compact_context(feedback, history, policy):
    """Keep latest feedback verbatim; bound redundant historical narrative only.

    No coordinates, IDs, contacts, accepted commands, or current errors are rounded,
    summarized by another model, or removed. If physics itself grows, the context
    grows with it: silently dropping physical state is never a compaction option.
    """
    if policy.get('version') != 1:
        raise ValueError('Unsupported fold context policy')
    if any(not isinstance(policy.get(k), int) or policy[k] < 1 for k in DEFAULT_POLICY if k != 'version'):
        raise ValueError('Compaction limits must be positive integers')
    recent, used = [], 0
    for number in range(len(history), max(0, len(history)-policy['recent_exchanges']), -1):
        exchange = history[number-1]
        result = exchange['harness_feedback']
        entry = dict(exchange=number, model_output=exchange['model_output'],
                     outcome={k: result[k] for k in ('ok', 'error', 'failed_command',
                              'model_claimed_done', 'model_reported_blocked') if k in result},
                     accepted_count=len(result.get('accepted_commands', [])))
        if 'probe_result' in result:
            entry['probe_outcome'] = {k: result['probe_result'][k] for k in ('ok', 'error', 'failed_command') if k in result['probe_result']}
        size = len(json.dumps(entry))
        if used + size > policy['recent_chars']:
            break
        recent.insert(0, entry)
        used += size
    # Preserve repeated failed actions as exact command/error pairs, not guesses
    # about why physics failed. Historical coordinates must not be reused blindly.
    failures = {}
    for number, exchange in enumerate(history, 1):
        result = exchange['harness_feedback']
        is_probe = 'probe_result' in result
        if is_probe:
            result = result['probe_result']
        if result['ok']:
            continue
        command = None
        try:
            proposal = json.loads(exchange['model_output'])
            index = result.get('failed_command', 0)-1
            if isinstance(proposal, dict) and index >= 0:
                command = proposal['probe' if is_probe else 'commands'][index]
        except (ValueError, TypeError, KeyError, IndexError):
            pass
        pair = dict(command=command, error=result.get('error', ''))
        key = digest(pair)
        old = failures.pop(key, None)
        failures[key] = dict(**pair, count=(old['count'] if old else 0)+1, last_exchange=number)
    memory, used = [], 0
    for entry in reversed(list(failures.values())):
        size = len(json.dumps(entry))
        if len(memory) >= policy['failure_entries']:
            break
        if used + size <= policy['failure_chars']:
            memory.insert(0, entry)
            used += size
    physics = {key: feedback[key] for key in ('state', 'layers', 'accepted_commands')}
    return dict(harness_feedback=feedback, recent_model_harness_exchanges=recent,
                failed_move_memory=memory,
                continuity=dict(version=1, exchanges=len(history), compacted_exchanges=len(history)-len(recent),
                    history_sha256=digest(history), physics_sha256=digest(physics),
                    accepted_count=len(feedback['accepted_commands']),
                    note=('Current harness_feedback is authoritative and exact. Planning undo removed mistaken actions; only its accepted_commands remain in the lesson. Older exchanges include undone actions and stale panel IDs. Continue from the restored sheet.' if any(h['harness_feedback'].get('undo_count') for h in history) else 'Current harness_feedback is authoritative and exact. Accepted commands have already executed. Historical command coordinates and panel IDs may be obsolete. Continue from the current sheet; compaction never unfolds or resets it.')))
