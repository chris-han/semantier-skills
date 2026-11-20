# Language and terminology — Chinese / bilingual reasoning

**Purpose:** preserve identical reasoning standards across English, Simplified Chinese and mixed-language inputs. This is a conditional reference, not a translation of every workflow or a new activation entry.

## Language selection (only ask if truly ambiguous)

1. Follow an explicit user instruction to answer in Chinese, English or another supported language. A language request overrides the request's surface language, not evidentiary boundaries.
2. Otherwise follow the language of the user's active *question or instruction*. A document, cited passage, code block or URL written in another language is source material and does not change the response language.
3. When the active instruction is genuinely mixed and no clear dominant language exists, use the established conversational language if known; otherwise answer briefly in the more prominent instruction language. Only ask for output-language clarification if it materially affects the deliverable.
4. Keep depth (L0–L3), lead workflow, Coach/Deliver mode, specialist loading, risk/stop thresholds and epistemic labels invariant under faithful translation. A Chinese question is not automatically a “simple” case, and an English document is not automatically an English response.
5. In Coach mode, ask **one** focused question in the chosen output language; do not stack bilingual questions or repeatedly re-ask merely to translate.

## Evidence and quotation fidelity

- Keep quotations, source spans, citations, identifiers, source dates, exact values, units, negation, modal verbs, and uncertainty qualifiers faithful. Preserve verbatim source text inside quotation marks; introduce any Chinese translation outside the quotation and label it **译文 / translation** when ambiguity matters.
- Separate the original claim from an analyst translation, paraphrase, reconstructed warrant or judgment. A translation is **not** new corroborating evidence or an independently verified fact.
- Check scope and polarity in both languages: “some” ≠ “all”, “may” ≠ “must”, “correlates” ≠ “causes”, “not proved” ≠ “proved false”, “合法” ≠ “合乎道德”.
- For factual disputes prefer original-language primary sources, and cite original locators even if the answer is Chinese. Do not translate code, commands, personal names, institutional legal names or formal labels without a user need.
- Avoid transliteration or an English word in every clause. Give an English term on first meaningful mention when it prevents confusion, then use the Chinese term.

## Compact terminology

| English | Preferred Chinese | Distinction to preserve |
| --- | --- | --- |
| claim / proposition | 主张／命题 | The statement being evaluated, not verified fact |
| premise | 前提 | Starting proposition, potentially false |
| assumption | 假设／隐含假设 | Accepted without direct proof in the argument |
| evidence / source | 证据／来源 | Evidence quality and source credibility differ |
| inference | 推断 | Step from stated facts or premises to conclusion |
| warrant | 论证担保／推理桥梁 | Why this evidence supports that claim |
| counterevidence | 反证／相反证据 | May refute, qualify, or only weaken a claim |
| qualifier / scope | 限定条件／适用范围 | Do not expand scope during translation |
| causation / correlation | 因果关系／相关性 | Correlation alone does not identify causality |
| uncertainty / unknown | 不确定性／未知 | UNKNOWN is not FALSE |
| falsification / revision trigger | 证伪条件／改判条件 | Evidence that would change the judgment |
| normative / empirical | 规范性／经验性 | Values and obligations differ from factual descriptions |
| organizational feedback | 组织反馈回路 | Only where a supported circular mechanism exists |
| cognitive offloading | 认知外包／认知卸载 | Do not presume skill-use necessarily improves learning |

## Chinese style and output

Use natural, unpretentious Chinese with the user's requested level of precision. Preserve named factual limitations. For deep audits, clearly distinguish **已核实／来源声称／推断／假设／尚不能判断** when needed; do not fill every answer with a table or checklist. English citations and technical terms remain as originals. For bilingual writing, honor the intended reader's language, not the author's current chat language, when the user explicitly requests a different target audience.

**If a significant language switch changes the claimed inference or evidence strength**, mark it as a translation/scope issue and reopen that specific claim, not the entire reasoning chain.
