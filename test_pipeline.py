import json
import sys

from data.ollama_gen import (
    generate_card_response,
    get_article_from_pool,
    run_quality_gate,
)


if __name__ == "__main__":
    if "--gate" in sys.argv:
        report = run_quality_gate()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        raise SystemExit(0)

    test_title, test_summary, test_rarity = get_article_from_pool()
    response = generate_card_response(test_title, test_summary, test_rarity)

    print(f"Article: {test_title} | Rarity: {test_rarity}")
    print("json" + json.dumps(response, indent=2, ensure_ascii=False))
