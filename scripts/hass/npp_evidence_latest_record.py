#!/usr/bin/env python3
"""Check the NPP receipt evidence builder with one offline fixture sequence."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hass.npp import evidence


EXPECTED = (
    "step 0 approval=2",
    "step 1 publish=change-2:abcdef0:seen",
    "step 2 fallbacks=['a-fallback', 'x-fallback']",
    "step 3 stage=ValueError:stages.outcome: invalid value stages=1",
    "step 4 stages=1 fallbacks=2",
    "step 5 drift=True,False",
    "step 6 approval=ValueError:approval.change_id: invalid value kept=2",
    "step 7 problems=0",
)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, add_help=False).parse_args(argv)
    failed = False

    def finding(reason):
        nonlocal failed
        failed = True
        print(f"FAIL {reason}")

    def report(step, detail, reason=None):
        line = f"step {step} {detail}"
        print(line)
        if reason is not None:
            finding(reason)
        if line != EXPECTED[step]:
            finding(f"evidence-changed {step}")

    try:
        builder = evidence.Evidence()
        builder.approval(1, 'Mike', 0, 'change-1', 'abcdef1')
        builder.approval(2, 'G', '2026-11-21T14:00:00Z', 'change-2', 'abcdef2')
        report(0, f"approval={builder.doc()['approval']['version']}")

        builder.publish('change-1')
        builder.publish('change-2', 'abcdef0', 'seen')
        publish = builder.doc()['publish']
        report(1, f"publish={publish['change_id']}:{publish['commit']}:{publish['live_verify']}")

        for code in ('x-fallback', 'a-fallback', 'x-fallback'):
            builder.fallback(code)
        report(2, f"fallbacks={builder.doc()['fallbacks']}")

        builder.stage('S1', 0, 5, 'ok')
        stage = 'accepted'
        try:
            builder.stage('S2', 0, 5, 'bad')
        except ValueError as exc:
            stage = f"ValueError:{exc}"
        report(3, f"stage={stage} stages={len(builder.doc()['stages'])}")

        snapshot = builder.doc()
        snapshot['stages'].append({'stage': 'S9'})
        snapshot['fallbacks'].append('z')
        detached = builder.doc()
        stages, fallbacks = len(detached['stages']), len(detached['fallbacks'])
        report(4, f"stages={stages} fallbacks={fallbacks}",
               'leaked-mutation 4' if (stages, fallbacks) != (1, 2) else None)

        builder.model('s5-copy', 'model-a', 'model-b')
        builder.model('s5-copy', 'model-a', None)
        drift = ','.join(str(row['drift']) for row in builder.doc()['models'])
        report(5, f"drift={drift}")

        approval = 'accepted'
        try:
            builder.approval(3, 'G', 0, 'change$3', 'abcdef3')
        except ValueError as exc:
            approval = f"ValueError:{exc}"
        report(6, f"approval={approval} kept={builder.doc()['approval']['version']}")

        problems = len(evidence.validate(builder.doc()))
        report(7, f"problems={problems}", 'invalid-doc' if problems else None)
    except Exception:
        # An incomplete step leaves the state unsuitable for subsequent checks.
        finding('check-error')

    print(f"{'FAIL' if failed else 'PASS'} npp_evidence_latest_record")
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
