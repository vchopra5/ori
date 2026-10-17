"""Iterative original LEGO designs, step feedback, and a local SQLite archive."""
import copy
import json
import math
import sqlite3
from pathlib import Path
from .lego import compile_plan, save_run


def revise(previous, proposal):
    """Keep the prefix before a one-based restart step; replace its suffix."""
    start = proposal.get('restart_from_step', 1)
    if type(start) is not int or start < 1 or start > len(previous.get('steps', [])) + 1:
        raise ValueError('restart_from_step must identify a step in the previous plan, or its next step')
    result = copy.deepcopy(proposal['plan'])
    prefix = previous.get('steps', [])[:start-1]
    retained = {s['piece'] for s in prefix}
    old_parts = {p['id']: p for p in previous.get('pieces', [])}
    new_parts = {p['id']: p for p in result['pieces']}
    if any(new_parts.get(key) != old_parts[key] for key in retained):
        raise ValueError('Cannot change a piece already placed before the restart step')
    result['steps'] = copy.deepcopy(prefix) + result['steps']
    return result


def prefix_plan(plan, steps):
    result = dict(plan, steps=steps)
    ids = {s['piece'] for s in steps}
    result['pieces'] = [p for p in plan['pieces'] if p['id'] in ids]
    return result


def test_steps(plan):
    """Validate each prefix and sample articulated movement at <=2 degree intervals."""
    checks = []
    for index, step in enumerate(plan['steps']):
        try:
            steps = copy.deepcopy(plan['steps'][:index+1])
            compile_plan(prefix_plan(plan, steps))
            samples = 0
            if step.get('action') == 'rotate_hinge':
                old = compile_plan(prefix_plan(plan, steps[:-1]))['hinge_angles'][step['piece']]
                angle = step['angle']
                samples = max(1, math.ceil(abs(angle-old)/2))
                for n in range(1, samples+1):
                    steps[-1]['angle'] = old+(angle-old)*n/samples
                    compile_plan(prefix_plan(plan, steps))
            checks.append(dict(step=index+1, passed=True, rotation_samples=samples))
        except (ValueError, KeyError, TypeError) as error:
            return dict(passed=False, failed_step=index+1, error=str(error), checks=checks)
    try:
        if len(plan['pieces']) != 10:
            raise ValueError('The final build must contain exactly 10 physical pieces')
        compile_plan(plan)
    except (ValueError, KeyError, TypeError) as error:
        return dict(passed=False, error=str(error), checks=checks)
    return dict(passed=True, checks=checks, limits='Simplified geometry; rotation sampled every <=2 degrees. No physical or insertion-path validation.')


def database(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS lego_trials (id INTEGER PRIMARY KEY, build_id TEXT NOT NULL, attempt INTEGER NOT NULL, proposal TEXT NOT NULL, feedback TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
    db.execute('CREATE TABLE IF NOT EXISTS lego_builds (id TEXT PRIMARY KEY, title TEXT NOT NULL, model TEXT NOT NULL, plan TEXT NOT NULL, validation TEXT NOT NULL, output_path TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
    return db


def run(client, prompt, output, db_path, model='gemini-4-argon', max_attempts=8):
    from google.genai import types
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    previous = {}
    history = prompt
    with database(db_path) as db:
        offset = db.execute('SELECT COALESCE(MAX(attempt),0) FROM lego_trials WHERE build_id=?', (output.name,)).fetchone()[0]
        for iteration in range(1, max_attempts+1):
            attempt = offset + iteration
            print(f'Gemini step-by-step trial {attempt} (this session {iteration}/{max_attempts})', flush=True)
            response = client.models.generate_content(model=model, contents=history,
                config=types.GenerateContentConfig(response_mime_type='application/json', max_output_tokens=32768))
            raw = response.text or ''
            (output/f'design-response-{attempt}.json').write_text(raw)
            try:
                proposal = json.loads(raw)
                candidate = revise(previous, proposal)
                previous = candidate
                feedback = test_steps(candidate)
            except (ValueError, KeyError, TypeError) as error:
                feedback = dict(passed=False, error=str(error))
            db.execute('INSERT INTO lego_trials(build_id,attempt,proposal,feedback) VALUES(?,?,?,?)',
                       (output.name, attempt, raw, json.dumps(feedback)))
            db.commit()
            print(json.dumps(feedback), flush=True)
            if feedback['passed']:
                report = save_run(previous, output)
                report.update(origin='original_design', model=model, step_validation=feedback)
                (output/'report.json').write_text(json.dumps(report, indent=2))
                (output/'step-validation.json').write_text(json.dumps(feedback, indent=2))
                db.execute('INSERT OR REPLACE INTO lego_builds(id,title,model,plan,validation,output_path) VALUES(?,?,?,?,?,?)',
                           (output.name, previous['title'], model, json.dumps(previous), json.dumps(feedback), str(output.resolve())))
                db.commit()
                return previous
            history = prompt+'\nCurrent full plan:\n'+json.dumps(previous)+'\nValidator feedback:\n'+json.dumps(feedback)+'\nRevise from any step you choose. Set restart_from_step and provide ONLY replacement suffix steps; full inventory is still required. Earlier steps are preserved. If necessary restart from step 1 and redesign.'
    raise RuntimeError('No passing design; trial feedback saved in database. No build was published.')
