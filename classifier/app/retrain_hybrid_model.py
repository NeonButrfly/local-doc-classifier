#!/usr/bin/env python3
import json

from hybrid_runtime import ensure_lightgbm_model, maybe_retrain_from_shadow_data


def main() -> int:
    result = ensure_lightgbm_model()
    if result.get("ok") and result.get("created"):
        print(json.dumps(result, indent=2))
        return 0

    retrain = maybe_retrain_from_shadow_data(min_rows=3)
    print(json.dumps(retrain, indent=2))
    return 0 if retrain.get("retrained") else 1


if __name__ == "__main__":
    raise SystemExit(main())
