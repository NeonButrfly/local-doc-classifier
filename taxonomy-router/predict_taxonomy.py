#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from pathlib import Path

import joblib

MODEL_PATH = Path("/opt/local-doc-classifier/config/taxonomy-router.joblib")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()

    model = joblib.load(MODEL_PATH)

    if isinstance(model, dict) and model.get("kind") == "tfidf_label_index":
        q = model["vectorizer"].transform([args.text])
        scores = (model["matrix"] @ q.T).toarray().ravel()
        labels = model["labels"]

        best = defaultdict(float)
        for score, label in zip(scores, labels):
            if score > best[label]:
                best[label] = float(score)

        results = [
            {"label": label, "score": score}
            for label, score in sorted(best.items(), key=lambda x: x[1], reverse=True)[:args.top]
        ]
    else:
        label = model.predict([args.text])[0]
        results = [{"label": str(label), "score": 1.0}]

    print(json.dumps({"ok": True, "results": results}, indent=2))

if __name__ == "__main__":
    main()
