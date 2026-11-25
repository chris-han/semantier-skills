# DeepTutor attribution

Portions adapted from HKUDS/DeepTutor, revision `341af371bf8143b2da3569084edf8e6cb46d7404`, under the included Apache License 2.0. Semantier modifications are identified below.

| Original path | Original Git blob | Symbols, destination and changes |
| --- | --- | --- |
| `deeptutor/learning/mastery.py` | `95d1e87b549a78138af735b21f66c74e455711a6` | compute_mastery and recency weights and caps → mastery.py. Reject out-of-range inputs; drop service references. |
| `deeptutor/capabilities/mastery/prompts/en/mastery_loop.yaml` | `65fe3f1ae287a0657d328bdd23b9515f1ba07215` | general and runtime_policy → prompts/teaching.en.md. Replace gated engine protocol with learner-directed practice and progress. |
| `deeptutor/capabilities/mastery/prompts/zh/mastery_loop.yaml` | `257c57512b3da775dc0ee464225a439853bcf694` | general and runtime_policy → prompts/teaching.zh.md. Same adaptation for Chinese. |
| `LICENSE` | `ae1dbfc5e74c6c9ebb3e46ea9ea8dde8a4a04ed8` | Apache License 2.0 → licenses/DeepTutor-Apache-2.0.txt, unchanged. |
