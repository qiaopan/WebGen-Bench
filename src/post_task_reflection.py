"""Post-task case reflection for continual long-memory construction.

Reflection is created only *after* a website receives its locked evaluation.  It is
an archive for later tasks, never feedback to regenerate the same website.  Raw
model output is retained even when a locator cannot be resolved exactly: losing a
useful case because an LLM expressed a locator differently is worse than recording
it with an explicit provenance warning.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


TROUBLESHOOTING_STEPS = """Troubleshooting order (work like a programmer looking for the cause, and only then write):
1) Read the tester's last steps and the answer: what was done, what appeared, where did it stop.
2) Read evaluator_log first. If the page raised an error, search the code for the text or the call
that produces it and read the function around it.
3) Find the element the tester used (label, placeholder, typed value) and follow its event handler
to what the user then sees (state update, message, navigation, dialog).
4) If something was not visible: find how the visibility of that content is controlled (conditional
rendering, a state-driven tab or section, hidden or display classes, an image source) and whether the
view the check looked at triggers it.
5) If nothing in what the tester saw or in the code explains the result, say there is no concrete
defect. Cite only code that is in the supplied files, and never claim that something is absent from
a file that may have been supplied only in part."""


REFLECTION_INSTRUCTIONS = """Produce one detailed post-task case reflection for a
continual website-generation memory system. The website has already received its
final locked evaluation and MUST NOT be repaired or regenerated. Use only the
supplied public requirement, GUI trajectory, final evaluation evidence and
screenshot-based appearance feedback. Never repeat hidden expected answers.

This is not a generic project summary. Preserve the task case: requirement scope,
feature object, user trigger, expected state change, observed result, and a
confirmed root cause or clearly labelled hypothesis.

Return two independent parts (a separate pass writes the functional lessons, one call per
failed/partial check, so it is not asked for here):
1) task_summary: concise requirement coverage, verified strengths, main functional
risks, and visible observations.
2) appearance_reflection: record only a concrete, task-specific visible gap between
the screenshot and the requirement: for example a required feature or content that
is not visible on the first screen shown, or a colour/layout requirement that is not
met. Generic remarks are the reviewer's stock wording and are NOT lessons: never turn them
into a case. Examples of stock remarks: "the page is sparse / minimal / basic",
"lacks modern flair, imagery, cards or richer visuals", "could be more polished or
engaging", "add more visual hierarchy or spacing".
If the colour and layout requirements are met and there is no concrete gap, return
null. Phrase preventative_action as a design requirement about what the page must
show (for example "show the contact details and the booking entry on the landing
page"). The screenshot shows only what is visible on screen; say "not visible", do
not infer that a feature is missing or broken. Do not infer functional behaviour
from a screenshot.
Return JSON only:
{"task_summary":{"requirement_coverage":str,"verified_strengths":[str],
"primary_functional_risks":[str],"primary_visual_observations":[str]},
"appearance_reflection":null|{"observed_result":str,"likely_cause_or_limitation":str,
"preventative_action":str,"verification":str,"transfer_limits":str,
"evidence_refs":[supplied refs]}}.
Evidence refs should use supplied refs, but
do not omit a useful concrete observation merely because its locator is uncertain."""


_FUNCTIONAL_FIELDS = (
    "feature_object", "user_trigger", "expected_state_change", "observed_result",
    "outcome", "likely_cause_or_limitation", "preventative_action", "verification",
    "transfer_limits",
)
_APPEARANCE_FIELDS = (
    "observed_result", "likely_cause_or_limitation", "preventative_action",
    "verification", "transfer_limits",
)


def _clean_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _task_summary(value: object) -> dict:
    value = value if isinstance(value, dict) else {}
    coverage = value.get("requirement_coverage", "")
    return {
        "requirement_coverage": coverage.strip() if isinstance(coverage, str) else "",
        "verified_strengths": _clean_strings(value.get("verified_strengths")),
        "primary_functional_risks": _clean_strings(value.get("primary_functional_risks")),
        "primary_visual_observations": _clean_strings(value.get("primary_visual_observations")),
    }


def _resolve_refs(refs: object, evidence: list[dict]) -> tuple[list[dict], str]:
    """Resolve exact or conventional locator variants without silently dropping case.

    A raw reflection remains archived even when this returns ``unresolved``.  Only
    ``exact_or_normalised`` items become strict extraction evidence.
    """
    if not isinstance(refs, list):
        return [], "unresolved"
    available = [item.get("ref") for item in evidence if isinstance(item.get("ref"), dict)]
    exact = {_json(ref): ref for ref in available}
    # Evaluator records expose their GUI transcript via ``content.evidence``.
    # A reflection model sometimes copies that path rather than the compact ref
    # object. It is still an unambiguous reference to supplied evidence.
    evidence_paths = {
        item["content"].get("evidence"): item["ref"]
        for item in evidence
        if isinstance(item.get("ref"), dict) and isinstance(item.get("content"), dict)
        and isinstance(item["content"].get("evidence"), str)
    }
    resolved: list[dict] = []
    seen: set[str] = set()
    for supplied in refs:
        if isinstance(supplied, str):
            match = evidence_paths.get(supplied)
            candidate = None
        elif isinstance(supplied, dict):
            candidate = supplied.get("ref") if isinstance(supplied.get("ref"), dict) else supplied
            match = exact.get(_json(candidate))
        else:
            continue
        if match is None:
            for ref in available:
                # Models commonly use check/message/result indices without the
                # wrapper kind/role.  Accept only an unambiguous conventional match.
                keys = ("check", "message_index", "result_index", "step_id")
                if isinstance(candidate, dict) and any(
                    key in candidate and candidate.get(key) == ref.get(key) for key in keys
                ):
                    match = ref
                    break
        if match is not None and _json(match) not in seen:
            resolved.append(match)
            seen.add(_json(match))
    return resolved, "exact_or_normalised" if resolved else "unresolved"


def _complete(item: object, fields: tuple[str, ...]) -> bool:
    return isinstance(item, dict) and all(
        isinstance(item.get(field), str) and item[field].strip() for field in fields
    )


def _normalise_functional(item: object, evidence: list[dict]) -> dict | None:
    if not _complete(item, _FUNCTIONAL_FIELDS):
        return None
    assert isinstance(item, dict)
    if item["outcome"].strip().lower() not in ("success", "partial", "failure"):
        return None
    refs, provenance_status = _resolve_refs(item.get("evidence_refs"), evidence)
    return {
        **{key: item[key].strip() for key in _FUNCTIONAL_FIELDS},
        "outcome": item["outcome"].strip().lower(),
        "evidence_refs": refs,
        "provenance_status": provenance_status,
        "accepted_for_memory": bool(refs),
    }


def _normalise_appearance(item: object, evidence: list[dict]) -> dict | None:
    if not _complete(item, _APPEARANCE_FIELDS):
        return None
    assert isinstance(item, dict)
    refs, provenance_status = _resolve_refs(item.get("evidence_refs"), evidence)
    return {
        "channel": "appearance",
        **{key: item[key].strip() for key in _APPEARANCE_FIELDS},
        "evidence_refs": refs,
        "provenance_status": provenance_status,
        "accepted_for_memory": bool(refs),
    }


CRITIQUE_INSTRUCTIONS = """You review ONE post-task reflection case for a website-generation
memory. You are given the PUBLIC requirement, the case, and the evaluation evidence
(the tester's steps and answers). Write your reasoning in "analysis" first (3-6
sentences), then give the verdict. Check in this order.
1. Unstated expectations. The tester's thoughts may quote labels, page names or
wording it expected. Those come from hidden expectations, not from the public
requirement. Find every name, label, wording or feature the case asserts that the
PUBLIC requirement does not state. If the case's only problem is such a mismatch,
the verdict is drop. If it also contains a real defect, rewrite it without them.
After removing the unstated expectations, if no concrete defect of the website is
left (the case would say only that it "differs" or "works"), the verdict is drop,
never rewrite.
2. Cause support. Is likely_cause_or_limitation supported by what the tester
actually did and saw? For a lookup that returned "not found" or nothing, state what
the tester typed, where that value could have come from (placeholder or sample text
on the page), and what the site failed to give a first-time visitor (for example no
sample record, or a placeholder that does not resolve). Do not guess about
persistence or logic unless the steps show it. If the case gives code_evidence, check
against the supplied code that the excerpt really explains the behaviour; if the code
shows a different cause, rewrite the cause and action to match the code.
3. Actionability. Would a developer who reads only preventative_action change the
code? If it only says to make something work reliably, correctly or as specified, it
is not a lesson: rewrite it in 1-2 sentences as a concrete, generalizable design
change (what to keep, add, show or pre-fill), without this site's business content,
page names or example values.
Return JSON only:
{"analysis":str,"verdict":"keep|rewrite|drop","reason":str,
"rewritten":null|{<only the fields you change, among feature_object,user_trigger,
expected_state_change,observed_result,likely_cause_or_limitation,
preventative_action,verification,transfer_limits>}}.
A rewritten case must not contain any name, label or wording that the public
requirement does not state. For drop, rewritten is null."""


def _critique_evidence(evidence: list[dict], *, appearance: bool) -> list[dict]:
    code = [] if appearance else [i for i in evidence if isinstance(i.get("ref"), dict)
                                   and i["ref"].get("kind") in ("code_manifest", "code_file")]
    outcome_by_index: dict[int, dict] = {}
    for item in evidence:
        ref, content = item.get("ref"), item.get("content")
        if isinstance(ref, dict) and ref.get("kind") == "evaluation_result" and isinstance(content, dict):
            outcome_by_index[ref.get("result_index")] = content
    picked = []
    for item in evidence:
        ref = item.get("ref")
        if not isinstance(ref, dict) or ref.get("kind") not in ("evaluation_result", "gui_trajectory", "evaluator_log"):
            continue
        result = outcome_by_index.get(ref.get("result_index"))
        if not isinstance(result, dict):
            continue
        is_appearance = result.get("check") == "appearance"
        if appearance and is_appearance and ref["kind"] == "evaluation_result":
            picked.append(item)
        elif not appearance and not is_appearance and result.get("outcome") != "passed":
            picked.append(item)
    guidance = [i for i in evidence if isinstance(i.get("ref"), dict) and i["ref"].get("kind") == "guidance_received"]
    return picked + code + guidance


def _critique(llm: Any, trajectory: Mapping[str, Any], evidence: list[dict],
              item: dict, fields: tuple[str, ...], *, appearance: bool) -> dict | None:
    """Second, single-purpose pass over one case. Returns the reviewed item, or None to drop it."""
    try:
        result = llm.generate("post_task_case_critique", {
            "instructions": CRITIQUE_INSTRUCTIONS,
            "public_requirement": str(trajectory["task_request"]),
            "case_type": "appearance" if appearance else "functional",
            "case": {**{key: item[key] for key in fields},
                     **({"code_evidence": item.get("code_evidence")} if not appearance else {})},
            "evidence": _critique_evidence(evidence, appearance=appearance),
        })
    except ValueError:
        return {**item, "critique": {"verdict": "error"}}
    verdict = str(result.get("verdict", "keep")).strip().lower()
    reason = str(result.get("reason", ""))
    if verdict == "drop":
        return None
    reviewed = dict(item)
    if verdict == "rewrite" and isinstance(result.get("rewritten"), dict):
        for key, value in result["rewritten"].items():
            if key in fields and isinstance(value, str) and value.strip():
                reviewed[key] = value.strip()
    reviewed["critique"] = {"verdict": verdict, "reason": reason}
    return reviewed


def _ground_code_evidence(item: dict, evidence: list[dict]) -> dict:
    """Deterministic check that a cited code excerpt really exists in the supplied file."""
    claim = item.get("code_evidence")
    if not isinstance(claim, dict):
        item["code_evidence"] = None
        return item
    file, snippet = str(claim.get("file", "")).strip(), str(claim.get("snippet", "")).strip()
    norm = lambda text: re.sub(r"\s+", " ", text).strip()
    files = {e["ref"]["path"]: e["content"] for e in evidence
             if isinstance(e.get("ref"), dict) and e["ref"].get("kind") == "code_file"}
    content = files.get(file) or next((text for path, text in files.items()
                                       if file and (path.endswith(file) or file.endswith(path))), None)
    grounded = bool(snippet and content is not None and norm(snippet) in norm(content))
    item["code_evidence"] = {"file": file, "snippet": snippet[:400], "grounded": grounded}
    item.setdefault("evidence_refs", []).append({"kind": "code_snippet", "file": file,
                                                 "snippet": snippet[:400], "grounded": grounded})
    if not grounded:
        item["likely_cause_or_limitation"] = "(unverified against code) " + item["likely_cause_or_limitation"]
    return item


_REQUIREMENT_CLAIM = re.compile(
    r"(specified|stated|required|listed|defined) (in|by) the (public )?requirement|"
    r"requirement (specifies|states|requires|lists|defines)", re.I)


_STOP = {"that", "this", "with", "from", "have", "should", "would", "could", "users", "user", "able",
         "website", "page", "pages", "site", "form", "shows", "show", "when", "then", "into", "each"}


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{4,}", text.lower()) if w not in _STOP}


def _ground_requirement_evidence(item: dict, requirement: str) -> dict:
    """Check a claimed requirement quote: it must appear in the requirement (fragments split
    by an ellipsis must appear in order) and be about this case; otherwise it is not credited."""
    norm = lambda text: re.sub(r"\s+", " ", text).strip().lower()
    claim = item.get("requirement_evidence")
    grounded = None
    if isinstance(claim, dict):
        quote = str(claim.get("quote", "")).strip()
        fragments = [norm(f) for f in re.split(r"\.{3}|\u2026", quote) if len(norm(f)) >= 3]
        haystack, position, found = norm(requirement), 0, bool(fragments)
        for fragment in fragments:
            index = haystack.find(fragment, position)
            if index < 0:
                found = False
                break
            position = index + len(fragment)
        about_case = bool(_content_words(quote) & _content_words(
            " ".join([item.get("feature_object", ""), item.get("expected_state_change", ""),
                      str(claim.get("site", ""))])))
        if not found:
            grounded = False
        elif about_case:
            grounded = True
        # A real sentence that is unrelated to this case is padding, not evidence: ignore it.
        if grounded is not None:
            item["requirement_evidence"] = {"quote": quote[:300], "site": str(claim.get("site", ""))[:300],
                                            "grounded": grounded}
            item.setdefault("evidence_refs", []).append({"kind": "requirement_quote", "quote": quote[:300],
                                                         "grounded": grounded})
        else:
            item["requirement_evidence"] = None
    else:
        item["requirement_evidence"] = None
    text = item["likely_cause_or_limitation"] + " " + item["preventative_action"]
    if grounded is False:
        item["likely_cause_or_limitation"] = ("(quoted requirement text not found in the requirement) "
                                              + item["likely_cause_or_limitation"])
    elif grounded is None and _REQUIREMENT_CLAIM.search(text):
        item["likely_cause_or_limitation"] = ("(claims the requirement asks for this, but no matching "
                                              "requirement quote was given) " + item["likely_cause_or_limitation"])
    return item


IMPLEMENTATION_INSTRUCTIONS = """You look for ONE implementation-approach lesson after a website
task. You are given the PUBLIC requirement, the failed functional checks (the tester's
steps and answers) and the website's own source code. Emit a framework/rendering-level
case only when the code directly proves that an already-written required interaction cannot
execute in its current rendering setup. Examples: state kept in static Astro frontmatter
instead of a hydrated component, a server-only component trying to handle a browser event,
or a component that is never mounted. Cite the exact code that demonstrates that execution
blocker. If the site merely lacks a link, button, route, event handler, or product-detail
control, that is a missing behaviour, not evidence that its framework is unsuitable: return
null here and let the ordinary functional reflection record the framework-neutral fix.

Do not infer that a static-site framework is incapable of navigation or product details:
ordinary links, static routes, and anchor links can satisfy those requirements. A different
framework is one optional implementation choice, never the conclusion unless the cited code
shows a rendering/execution blocker that the current setup cannot support. Give code_evidence
= {"file": <path as supplied>, "snippet": <verbatim excerpt of 1-6 lines>}. If the failures
are not caused by how the site is built, or the code does not show such a blocker, return null.
The evidence may include guidance_received: the implementation guidance this website was built with. If the
way the site was built follows from that guidance in a way that caused a failure, write the lesson as a
companion requirement that keeps what the guidance asks AND the missing part; never advise ignoring or
replacing the guidance.
[[TROUBLESHOOTING]]

Cause discipline: the cause must be something the code shows AND that explains what the tester
actually experienced (the steps, the answer, the evaluator_log). Do not audit the code against the
guidance or invent requirements the checks never exercised (for example a backend or persistence
when no failed check needed it); the guidance may only be mentioned when it explains how the site
came to be built the way it is. If the failures are about a hidden section or view (content only
reachable after a click while the check looked at the landing view), name that structure as the
cause.
Fix within reach: the generator writes only the files listed in code_manifest.generator_written_files;
every other project file (for example configuration it left as the starting template made it) stays as it
is unless a lesson names the change. When the cause is established, preventative_action must be a change
the generator can make by writing its own files: name the file and what it must contain, or an
implementation that works with what the project already declares (code_manifest dependencies). Wording
such as "ensure X is correctly installed, configured or imported" names no change and is not a lesson.
The preventative_action must name the concrete code-level execution fix. It may name a
framework or rendering choice only when the cited code proves that choice is necessary;
otherwise state a framework-neutral requirement such as mounting the existing handler or
rendering a real navigation control. setup_history is observational context only, not proof
that one framework is superior. Cite setup_evidence only when it supports, but never creates,
a conclusion already established by the code mechanism. Return JSON only:
{"implementation_reflection":null|{"feature_object":str,"user_trigger":str,
"expected_state_change":str,"observed_result":str,"likely_cause_or_limitation":str,
"preventative_action":str,"verification":str,"transfer_limits":str,
"code_evidence":{"file":str,"snippet":str},
"setup_evidence":null|{"setup":str,"runs":int}}}."""


def _ground_setup_evidence(item: dict, history: dict) -> dict:
    """The cited setup and run count must match the automatic statistics."""
    claim = item.get("setup_evidence")
    if not isinstance(claim, dict):
        item["setup_evidence"] = None
        return item
    entry = history.get(str(claim.get("setup", "")))
    grounded = bool(entry) and claim.get("runs") == entry["runs"]
    item["setup_evidence"] = {"setup": str(claim.get("setup", "")), "runs": claim.get("runs"),
                              "grounded": grounded, "history": entry if grounded else None}
    item.setdefault("evidence_refs", []).append({"kind": "setup_statistics", "setup": str(claim.get("setup", "")),
                                                 "grounded": grounded})
    if not grounded:
        item["likely_cause_or_limitation"] = "(setup statistics not verified) " + item["likely_cause_or_limitation"]
    return item


_FRAMEWORK_CHOICE = re.compile(
    r"\b(?:framework|rendering|static\s+(?:astro|site)|client[- ]rendered|hybrid|hydration|"
    r"astro\s+island|react|vite|vue|next\.js)\b", re.I)
_EXECUTION_BLOCKER = re.compile(
    r"\b(?:frontmatter|non[- ]hydrated|not\s+hydrated|server[- ]only|server[- ]rendered|"
    r"never\s+mounted|cannot\s+(?:run|execute)|does\s+not\s+execute|static\s+state)\b", re.I)


def _framework_claim_needs_execution_evidence(candidate: Mapping[str, Any]) -> bool:
    """Reject a framework prescription unless its cited code shows an execution blocker.

    Missing links, routes, buttons, or handlers are ordinary functional omissions. They do
    not establish that the selected framework caused the failure. This guard deliberately
    keeps the implementation-memory channel narrower than ordinary functional reflection.
    """
    text = " ".join(str(candidate.get(field, "")) for field in (
        "likely_cause_or_limitation", "preventative_action", "verification", "transfer_limits"))
    if not _FRAMEWORK_CHOICE.search(text):
        return False
    code = candidate.get("code_evidence")
    snippet = str(code.get("snippet", "")) if isinstance(code, Mapping) else ""
    return not _EXECUTION_BLOCKER.search(text + "\n" + snippet)


_PERSISTENCE = re.compile(
    r"\b(back-?end|end-?points?|api|apis|database|persist\w*|server-side|shared data source|real server)\b", re.I)
_REWRITE_FIELDS = ("observed_result", "likely_cause_or_limitation", "preventative_action", "verification",
                   "transfer_limits")

IMPLEMENTATION_REWRITE_INSTRUCTIONS = """The lesson below mentions a backend, endpoint, database or persistence, but nothing in the
public requirement or in the tester's evidence involves it. Rewrite the listed fields so that they
contain no such requirement, keeping every other point (the concrete cause the code shows and the
concrete fix) unchanged. Return JSON only: {"rewritten": {<field>: <text>}} with the same fields."""


def _drop_unsupported_persistence(llm: Any, candidate: dict, requirement: str, evidence: list[dict]) -> dict | None:
    """An implementation lesson may not demand a backend, endpoint or persistence unless the public
    requirement or the failed checks' evidence involves it (the model tends to add it on its own)."""
    def unsupported(item: dict) -> bool:
        return any(_PERSISTENCE.search(str(item.get(f, ""))) for f in _REWRITE_FIELDS)

    if not unsupported(candidate):
        return candidate
    support = requirement + " " + " ".join(_json(e.get("content", "")) for e in evidence)
    if _PERSISTENCE.search(support):
        return candidate
    try:
        result = llm.generate("post_task_implementation_rewrite", {
            "instructions": IMPLEMENTATION_REWRITE_INSTRUCTIONS,
            "lesson": {f: candidate[f] for f in _REWRITE_FIELDS}})
        rewritten = result.get("rewritten") if isinstance(result, dict) else None
    except ValueError:
        rewritten = None
    if isinstance(rewritten, dict):
        for field in _REWRITE_FIELDS:
            if isinstance(rewritten.get(field), str) and rewritten[field].strip():
                candidate[field] = rewritten[field].strip()
    # Whatever the model left: remove sentences that still demand it; the lesson needs its action.
    for field in _REWRITE_FIELDS:
        sentences = re.split(r"(?<=[.!?])\s+", str(candidate.get(field, "")))
        candidate[field] = " ".join(x for x in sentences if not _PERSISTENCE.search(x)).strip()
    candidate["persistence_removed"] = True
    if not candidate["preventative_action"] or not candidate["likely_cause_or_limitation"]:
        return None
    return candidate


FUNCTIONAL_CASE_INSTRUCTIONS = """You write ONE functional lesson for a continual website-generation
memory. You are given ONE specific functional check that did NOT pass (its own tester steps, answer and
evaluation result), the website's own source, and (when delivered) the guidance this website was built
with. Evidence for any OTHER check is never supplied here; write about this check only.

feature_object, user_trigger and expected_state_change must state the required behaviour of one whole
feature in requirement wording: what a user of the finished site can do and what the page must then show
(for example "submitting the lead form with valid information shows a confirmation message"), never only
the sub-step where it broke, and never in test-procedure wording. Put the broken sub-step (for example
"the phone field rejected a valid 10-digit number") in observed_result and likely_cause_or_limitation.
Write preventative_action in 1-2 sentences as a generalizable implementation requirement that applies to
any website with the same kind of feature: name the kind of control or behaviour, not this site's business
content, page names or example values (those stay in observed_result and the cause).

Topic discipline: feature_object must be the feature that THIS check's own tester steps and answer are
about, never a different feature you happen to find described in the code. Do not use the code to invent
a topic; use it only to explain a defect already visible in this check's own steps and answer. If this
check's own steps and answer are too thin to identify a concrete defect (for example the tester answered
from one screenshot with no interaction, or a one-line judgement with no described problem), return null
for this check instead of writing about anything else.

Check identity: this check's own task and expected result are stated in the first tester message of
its trajectory. Read them first; feature_object must be the feature THAT task names. The tester often
passes through other features on the way (for example opening a testimonials tab while looking for
navigation links); a defect noticed there belongs to that other feature's own check, which may well have
passed, so do not write it here. If the only defect you can see concerns a different feature than this
check's task, return null.

Missing feature: the feature this check asks for (named in its own task and expected result) may not
exist in the website at all, so the tester wandered into some other page and tried whatever controls
were there. Check the supplied code_manifest and code for that feature (a page, route, navigation item,
section or component for it). If the code shows it is absent, the absence IS the established cause:
feature_object is the feature this check asked for, observed_result says the site has no such feature
and briefly where the tester looked instead, preventative_action requires the site to provide every
content section or feature the requirement lists with its own reachable entry point, and code_evidence
quotes the navigation or route list that lacks it. Do not attribute the failure to the unrelated
control the tester happened to try; a defect in that control belongs to the check about that control.

Infrastructure, provider, port and timeout failures are not website lessons.

Evaluator log: evidence of kind evaluator_log holds the error lines of that check's own test
run. When it shows an error raised by the page itself (for example a browser dialog that the
page opened and that blocked the tester), that is the concrete cause: state it as the cause
and write the lesson as what the page must do instead. Errors from the test infrastructure
(connection, port, timeout, provider) are not website lessons.

[[TROUBLESHOOTING]]

Unexercised checks: if the tester answered from the first screenshot without using the feature,
or the run ended after its first action with no answer and the evaluator log shows no error
raised by the page, the check was not exercised. Write NOTHING for such a check (the "one
reflection for EACH partial or failed check" rule does not apply to it).
If every functional check passed, return an empty functional_reflections list.

Attribution rules: the failure_type / reached_target_action / logic_failure_observed
labels are coarse automatic labels, not ground truth; the GUI trajectory is the
ground truth. Name as cause only a defect that is actually visible in the trajectory
(for example valid input rejected, form cleared without confirmation, lookup
returning "not found", missing element). If the trajectory shows no concrete defect
(the agent simply ran out of interactions), say so and label any cause a hypothesis.
Do not treat a label alone as proof that the website is wrong or right.
The numbered boxes and labels in the tester's screenshots are drawn by the test tool to name elements;
they are not part of the website. A cause about those labels, or about the tester failing to find or
identify an element that the code does render, is a tester limitation, not a website defect.

Code attribution (optional): the supplied code_manifest and code_file evidence is the
website's own source. Use it only when the code really explains the observed
behaviour, for example a form with no submit handler, a component that is never
rendered, or hard-coded or missing data. Then give code_evidence = {"file": <path as
supplied>, "snippet": <a verbatim excerpt of 1-6 lines from that file>} and state
the lesson as what the implementation must contain (for example "every form needs a
client-side submit handler that shows a confirmation; a statically rendered page has
no client state unless a client script or hydrated component is added"), including
the implementation approach itself (framework or rendering mode) when it is the
reason. Many failures are not caused by a specific piece of code (the tester ran out
of interactions, the requirement is ambiguous, a feature exists but is not visible
where the tester looked): for those set code_evidence to null and do not stretch to
find a code cause. A missing code_evidence is always acceptable; a forced one is not.

Screenshots: the last screenshots the tester saw for this check are attached as images
(listed in attached_screenshots). Compare them with what the code says should be on screen.
When the code does implement the expected behaviour but the screenshot does not show it,
the cause is usually visual rather than logical. Trace it like a developer: start from the element
that should show the content and list the style rules that decide how it is drawn, in order - its
own component styles, then each parent container, then the global stylesheets the entry files
import (code_manifest.global_style_rules lists, as measured facts, every declaration those
stylesheets make on :root, html, body or #app). The rule that finally decides the element's
colour, size or visibility is the cause; quote it as code_evidence. Do this across all supplied
files before concluding that the logic is missing.

Cause confidence: set cause_confidence to "established" only when the screenshots, the
tester's own steps or a verbatim code excerpt show the cause. If you cannot point to such
evidence, set it to "uncertain" and say in likely_cause_or_limitation that the cause is not
established; do not present a plausible guess as the cause.
Two consistency checks before you choose "established": (1) if likely_cause_or_limitation uses
hedged wording (appears, seems, likely, may, might, probably, possibly), the cause is not
established - set "uncertain". (2) The quoted evidence must itself show the stated cause, not merely
be real code from a nearby place: a claim that something is missing needs evidence where it would
have to appear (the routes, the navigation, the component that should render it); a claim about
what the user saw needs the code that decides it. If the quote is genuine but does not show the
cause, set "uncertain".

Do not write stock advice such as "ensure the feature works correctly" or "follow
best practices" in any field.

Fix within reach: the generator writes only the files listed in code_manifest.generator_written_files;
every other project file (for example configuration it left as the starting template made it) stays as it
is unless a lesson names the change. When the cause is established, preventative_action must be a change
the generator can make by writing its own files: name the file and what it must contain, or an
implementation that works with what the project already declares (code_manifest dependencies). Wording
such as "ensure X is correctly installed, configured or imported" names no change and is not a lesson.

Actionability check: before writing preventative_action, ask whether a developer who
reads only that sentence would change the code. A sentence that only says something
must work "reliably", "correctly" or "as specified" restates the requirement and is
not a lesson; rewrite it as the concrete design change (what to keep, add, show or
pre-fill).

Concrete UI implementation: when the established cause is a client-side interaction
or a missing view transition, preventative_action must name the smallest supported
Vue code construction, not only the desired behaviour. For a view switch, name
`ref` state plus `v-if`; for a form result, name a submit handler that updates state
plus a `v-if` result/message; for a rendered collection, name a local array plus
`v-for`. Use these only where the supplied code and this check support them. Do not
write a vague substitute such as "ensure the interaction is configured correctly".
The later memory path preserves these construction names during compression.

Lookup failures: when a lookup or search returns "not found" or nothing, look at what
the tester typed and where that value could have come from (placeholder text, sample
text on the page). State the cause as what the site failed to give a first-time
visitor (for example no sample record, or a placeholder that does not resolve), not
as a guess about persistence or logic. The preventative_action then says what a
first-time visitor needs (for example seeded sample records and a visible sample
identifier that really resolves).

Requirement grounding: the evaluator's own thoughts may quote labels, page names or
wording it expected. For every functional case decide whether that expectation is
actually written in the public requirement. If it is, give requirement_evidence =
{"quote": <a verbatim phrase copied from the public requirement>, "site": <what the
website shows instead>} and write the lesson as following the requirement's own
wording. If it is NOT written in the public requirement, never say or imply that the
requirement asked for it: set requirement_evidence to null, and either write the
lesson as a general convention that most websites follow (for example plain,
conventional names for main sections) or leave the check out when the expectation is
only this one task's particular wording.

Lesson scope: decide from where the cause lives. If the cause is in something every page shares (the
entry file, a global stylesheet, the router or navigation, the root layout or app shell), the same
cause would affect every page, so set "scope" to "site_wide". If the cause is inside one feature's own
component or logic, set "feature". Site-wide lessons are offered to every later task; feature lessons only to
tasks with a similar feature.

Investigation order: before writing the lesson, work through these steps in order and record what
you found at each one in "investigation" (one or two sentences per step, citing the evidence you used):
1. task: the check's own task and expected result (first tester message) and the tester's final answer
   and stated reason.
2. reached_target: whether the tester actually reached the page, control or content the task is about,
   or stopped earlier (ran out of interactions, wandered to another feature, the page was still
   loading, an evaluator or driver error). If it never reached it, say WHY, using step 5: when the
   page the tester was on offers no entry point to the target (no link, button or menu item leads
   there), not reaching it is itself a website defect that can be established; only when an entry
   point existed and the tester did not use it (or ran out of interactions before using it) is
   nothing about the website established.
3. screenshots: what the attached screenshots actually show compared with what the task expected
   (content present, missing, blank, unreadable, wrong colour, wrong page).
4. errors: any build, console or evaluator error in the evidence, and the measured facts in
   code_manifest.imports_not_in_package_json (packages the source imports that package.json does not
   declare); write "none" if there is none.
5. code_path: follow the chain the feature needs in the source and say where it holds or breaks:
   route or section exists -> it is linked from navigation or the page the tester was on -> the
   component is mounted -> its data or handler is present -> it is rendered. A feature claimed absent
   must be shown absent where it would have to appear.
6. style_trace: whenever the code has the content (step 5 reaches "rendered") but the screenshot shows
   that place blank, empty or unreadable - note that text drawn in the same colour as its background
   looks exactly like an empty area in a screenshot, so a blank area is not proof that nothing is there -
   list, for the element that should show it, the text colour and background set by (a) the element's
   own styles, (b) each parent container, (c) the global stylesheets the entry files import
   (code_manifest.global_style_rules), each with file and rule; then name the rule that decides what
   is drawn. Otherwise write "not applicable".
7. candidates: name two or three possible causes (for example absent feature, unreachable feature,
   unreadable styling, broken handler, tester limitation) and for each say which evidence above
   supports or rules it out.
8. conclusion: the one cause that survives step 7 with direct evidence. "established" means a defect
   in the WEBSITE is established; if the surviving cause is a tester limitation (ran out of
   interactions, did not use an existing entry point, driver error), that is not a website defect, so
   cause_confidence is "uncertain" however sure you are about it. If more than one survives, or
   the only support is the tester's impression, set cause_confidence "uncertain". Do not use hedged
   wording (appears, seems, likely, may, might, probably) for an established cause.
9. fix_check: state the concrete change to THIS site's code that preventative_action implies (file and
   what changes) and whether, given steps 1-8, that change alone would make this check pass. If it
   would not (the cause lies elsewhere, or the tester never reached the target), rewrite the lesson so
   it addresses the cause that would, or set cause_confidence "uncertain".

Return null when the evidence gives no usable lesson for this check (only infrastructure failure, or an
unexercised check). Return JSON only:
{"functional_reflection":null|{"investigation":{"task":str,"reached_target":str,"screenshots":str,
"errors":str,"code_path":str,"style_trace":str,"candidates":str,"conclusion":str,"fix_check":str},
"feature_object":str,"user_trigger":str,
"expected_state_change":str,"observed_result":str,
"outcome":"partial|failure","likely_cause_or_limitation":str,
"cause_confidence":"established|uncertain","scope":"site_wide|feature",
"preventative_action":str,"verification":str,"transfer_limits":str,
"code_evidence":null|{"file":str,"snippet":str},
"requirement_evidence":null|{"quote":str,"site":str},
"evidence_refs":[supplied refs]}}."""


def _last_screenshots(check: Mapping[str, Any], count: int = 2) -> list[str]:
    """The last screenshots the tester saw for one check (next to its interact_messages.json)."""
    path = check.get("evidence") if isinstance(check, Mapping) else None
    if not isinstance(path, str):
        return []
    shots = sorted(Path(path).parent.glob("screenshot*.png"),
                   key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    return [str(p) for p in shots[-count:]]


def _check_own_evidence(evidence: list[dict], index: int) -> list[dict]:
    """Evidence for ONE functional check: its own evaluation_result/gui_trajectory/evaluator_log
    (matched by result_index) plus the site's code. guidance_received is deliberately left out here:
    it describes the whole site, not this check, and the model would otherwise borrow a different,
    more concrete-looking topic from it instead of writing about this check (or returning null)."""
    shared_kinds = ("code_manifest", "code_file")
    own_kinds = ("evaluation_result", "gui_trajectory", "evaluator_log")
    return [item for item in evidence if isinstance(item.get("ref"), dict) and (
        item["ref"].get("kind") in shared_kinds
        or (item["ref"].get("kind") in own_kinds and item["ref"].get("result_index") == index))]


def _check_own_text(own_evidence: list[dict], indices: int | set[int]) -> str:
    """The tester's own words for one check (or, given a set, every check in it): not the result
    dict's bookkeeping fields (file paths, stage/type labels), which would otherwise pollute a
    vocabulary comparison with generic matches unrelated to what the tester actually did or saw."""
    wanted = {indices} if isinstance(indices, int) else set(indices)
    parts = []
    for item in own_evidence:
        ref, content = item.get("ref"), item.get("content")
        if not isinstance(ref, dict) or ref.get("result_index") not in wanted:
            continue
        if ref.get("kind") == "evaluation_result" and isinstance(content, dict):
            parts.append(str(content.get("answer", "")))
        elif ref.get("kind") in ("gui_trajectory", "evaluator_log"):
            parts.append(str(content))
    return " ".join(parts)


_TOPIC_BOILERPLATE = {"answer", "answered", "action", "thought", "check", "verify", "verified", "verifying",
                      "checking", "needed", "already", "result", "results", "partial", "failed", "passed",
                      "outcome", "target", "reached", "achieved", "expected", "tester", "interact",
                      "visible", "visibly", "visibility", "component", "components", "state", "states",
                      "required", "requirement", "requirements", "feature", "features", "section", "sections"}


def _shares_topic(check_text: str, case: Mapping[str, Any], fields: tuple[str, ...]) -> bool:
    """Deterministic topic-drift guard: when the model has nothing concrete to say about the check(s)
    it was actually given, it will sometimes borrow a different, more concrete-looking topic from the
    site's code instead of admitting that. Require the case to share real vocabulary with what the
    tester actually did or saw; a case that shares none of it is not trusted, whatever it claims."""
    check_words = _content_words(check_text) - _TOPIC_BOILERPLATE
    if not check_words:
        return True  # too little tester text to judge by; do not block on this signal alone
    case_words = _content_words(" ".join(str(case.get(f, "")) for f in fields)) - _TOPIC_BOILERPLATE
    return bool(check_words & case_words)


# Why each failed/partial check produced no case in the latest _functional_cases call (diagnostics only).
LAST_FUNCTIONAL_SKIPS: list[dict] = []


def _functional_cases(llm: Any, trajectory: Mapping[str, Any], evidence: list[dict],
                      checks: list | None) -> list[dict]:
    """One model call per failed/partial functional check, each seeing only that check's own evidence.
    Replaces a single batched call, which had matched a case to the wrong check when several checks'
    trajectories were supplied together (the model tends to write about whichever is most salient)."""
    if not isinstance(checks, list):
        return []
    functional = []
    skipped = LAST_FUNCTIONAL_SKIPS
    skipped.clear()
    for index, check in enumerate(checks):
        if not isinstance(check, dict) or check.get("check") == "appearance" or check.get("outcome") == "passed":
            continue
        own_evidence = _check_own_evidence(evidence, index)
        screenshots = _last_screenshots(check)
        try:
            result = llm.generate("post_task_functional_case", {
                "instructions": FUNCTIONAL_CASE_INSTRUCTIONS,
                "public_task_requirement": str(trajectory["task_request"]),
                "check_index": index, "check_outcome": check.get("outcome"),
                "attached_screenshots": [Path(p).name for p in screenshots],
                "evidence": own_evidence, "_images": screenshots})
        except ValueError as error:
            skipped.append({"check_index": index, "reason": f"model call failed: {str(error)[:200]}"})
            continue
        item = result.get("functional_reflection") if isinstance(result, dict) else None
        if not isinstance(item, dict):
            skipped.append({"check_index": index, "reason": "model returned null"})
            continue
        # Format repair: the model sometimes closes "investigation" too late, nesting every case field
        # inside it. Lift those fields back to the case level (content unchanged).
        investigation = item.get("investigation")
        if isinstance(investigation, dict) and "feature_object" not in item and "feature_object" in investigation:
            steps = ("task", "reached_target", "screenshots", "errors", "code_path", "style_trace",
                     "candidates", "conclusion", "fix_check")
            item = {**{k: v for k, v in investigation.items() if k not in steps},
                    "investigation": {k: investigation[k] for k in steps if k in investigation}}
        # Deterministic topic-drift guard: the instructions ask the model to write about this check's
        # own steps/answer only, or return null when they are too thin -- but a model with no concrete
        # defect to report will sometimes borrow a different, more concrete-looking topic from the
        # site's code instead of returning null. Require the case to share real vocabulary with this
        # check's own text; a case that shares none of it is not trusted, whatever the model claims.
        if not _shares_topic(_check_own_text(own_evidence, index), item,
                             ("feature_object", "user_trigger", "observed_result")):
            skipped.append({"check_index": index, "reason": "topic guard: shares no words with this check",
                            "feature_object": str(item.get("feature_object"))[:120]})
            continue
        normalised = _normalise_functional(item, own_evidence)
        if normalised is None:
            skipped.append({"check_index": index, "reason": "normalise rejected the case"})
            continue
        normalised["check_index"] = index
        normalised["investigation"] = item.get("investigation")
        normalised["code_evidence"] = item.get("code_evidence")
        normalised["requirement_evidence"] = item.get("requirement_evidence")
        # "uncertain": kept on record but archived, so a guessed cause never reaches a later prompt.
        normalised["cause_confidence"] = ("uncertain" if str(item.get("cause_confidence", "")).strip().lower()
                                          == "uncertain" else "established")
        # A site-wide lesson is stored as an implementation case so it reaches the common pool, which every
        # later task sees and which ranks lessons by occurrence x severity rather than feature similarity.
        normalised["scope"] = "site_wide" if str(item.get("scope", "")).strip().lower() == "site_wide" else "feature"
        functional.append(_ground_requirement_evidence(
            _ground_code_evidence(normalised, own_evidence), str(trajectory["task_request"])))
    return _choose_site_wide(llm, route_scope(llm, functional, evidence))


SITE_WIDE_CHOICE_INSTRUCTIONS = """Several lessons from ONE website were marked site-wide. Group the lessons that
state the same underlying site-wide requirement (the same cause in the same shared part of the site);
lessons whose causes differ are different groups. In each group choose the ONE lesson that is most
purely about the whole site: prefer the lesson that names no single feature over one written for one
page or feature; when every lesson in the group mentions a feature, choose the one with the least
feature-specific detail. Every index appears in exactly one group. Return JSON only:
{"groups":[{"indices":[int],"chosen":int,"reason":str}]}."""


SCOPE_ROUTING_INSTRUCTIONS = """You decide where ONE lesson from a website-generation memory is stored.
"site_wide": the cause lies in something every page of a website shares, so the same cause would
affect other pages or features of any later website too; such lessons are offered to every later task.
"feature": the cause lies inside one feature's own component or logic, so the lesson only matters to a
later website with a similar feature. You get the lesson, its cause, its code evidence, and a measured
fact: whether the code evidence comes from a file every page shares (entry file, root component,
router, or a global stylesheet an entry file imports). Judge whether the same cause would reach other
pages; the fact is evidence, not the answer. A page or feature that is simply missing is a "feature"
lesson even when the evidence quotes a shared file (for example a route or menu list that lacks it):
the shared file only shows the absence. "site_wide" is for a rule or setup in a shared file that itself
breaks or hides content on several pages. Return JSON only: {"scope":"site_wide|feature","reason":str}."""

_SHARED_NAME = re.compile(r"(^|/)(main|index|App)\.(ts|tsx|js|jsx|vue|astro)$|(^|/)router/|^index\.html$")


def _shared_file(path: str, evidence: list[dict]) -> bool:
    """Code fact: is this file shared by every page (entry, root component, router, or a global stylesheet
    that an entry file imports)?"""
    path = str(path or "").strip()
    if not path:
        return False
    if _SHARED_NAME.search(path):
        return True
    for item in evidence:
        ref, content = item.get("ref"), item.get("content")
        if isinstance(ref, dict) and ref.get("kind") == "code_manifest" and isinstance(content, dict):
            for rule in content.get("global_style_rules") or []:
                if str(rule).startswith(path + " ") and "imported by: no entry file" not in str(rule):
                    return True
    return False


def route_scope(llm: Any, functional: list[dict], evidence: list[dict]) -> list[dict]:
    """Separate, single-purpose routing call per lesson: site-wide (common pool) or feature (feature
    match). Writing the lesson and judging its reach in one call left global causes marked "feature"."""
    for case in functional:
        code = case.get("code_evidence") if isinstance(case.get("code_evidence"), dict) else {}
        shared = _shared_file(code.get("file", ""), evidence)
        try:
            result = llm.generate("case_scope_routing", {
                "instructions": SCOPE_ROUTING_INSTRUCTIONS,
                "lesson": {k: case.get(k) for k in ("feature_object", "observed_result",
                                                     "likely_cause_or_limitation", "preventative_action")},
                "code_evidence": {"file": code.get("file"), "snippet": code.get("snippet")} if code else None,
                "code_evidence_from_shared_file": shared})
        except ValueError:
            result = {}
        scope = str(result.get("scope", "")).strip().lower() if isinstance(result, dict) else ""
        if scope in ("site_wide", "feature"):
            case["scope"] = scope
            case["scope_reason"] = str(result.get("reason", ""))[:300]
        case["code_evidence_from_shared_file"] = shared
    return functional


def _choose_site_wide(llm: Any, functional: list[dict]) -> list[dict]:
    """Keep one site-wide case per distinct site-wide lesson: it goes to the common pool as an
    implementation case; the other cases of that lesson stay feature cases, so the feature lessons they
    also carry remain retrievable by feature match, and the feature pool is not emptied."""
    marked = [i for i, case in enumerate(functional) if case.get("scope") == "site_wide"]
    chosen: set[int] = set(marked)
    if len(marked) > 1:
        try:
            result = llm.generate("site_wide_choice", {
                "instructions": SITE_WIDE_CHOICE_INSTRUCTIONS,
                "lessons": [{"index": i, "feature_object": functional[i]["feature_object"],
                             "preventative_action": functional[i]["preventative_action"]} for i in marked]})
        except ValueError:
            result = {}
        groups = [g for g in (result.get("groups") or []) if isinstance(g, dict)] if isinstance(result, dict) else []
        picked = {g.get("chosen") for g in groups if g.get("chosen") in marked}
        covered = {i for g in groups for i in (g.get("indices") or []) if i in marked}
        # Anything the model left out of every group stays site-wide rather than being silently demoted.
        chosen = picked | (set(marked) - covered) if picked else {marked[0]}
        for g in groups:
            if g.get("chosen") in chosen:
                functional[g["chosen"]]["site_wide_choice_reason"] = str(g.get("reason", ""))[:300]
    for i, case in enumerate(functional):
        if i in chosen:
            if not case["feature_object"].startswith("[implementation]"):
                case["feature_object"] = "[implementation] " + case["feature_object"]
        else:
            case["scope"] = "feature"
    return functional


def _implementation_case(llm: Any, trajectory: Mapping[str, Any], evidence: list[dict], checks: object,
                         history: dict | None = None) -> dict | None:
    """Separate, focused call: does how the site is built explain the failures?"""
    has_failure = isinstance(checks, list) and any(
        isinstance(c, dict) and c.get("check") != "appearance" and c.get("outcome") != "passed" for c in checks)
    has_code = any(isinstance(e.get("ref"), dict) and e["ref"].get("kind") == "code_file" for e in evidence)
    if not (has_failure and has_code):
        return None
    result = llm.generate("post_task_implementation_reflection", {
        "instructions": IMPLEMENTATION_INSTRUCTIONS,
        "public_requirement": str(trajectory["task_request"]),
        "evidence": _critique_evidence(evidence, appearance=False),
        "setup_history": history or {}})
    raw = result.get("implementation_reflection") if isinstance(result, dict) else None
    if not isinstance(raw, dict):
        return None
    candidate = _normalise_functional({**raw, "outcome": "partial", "evidence_refs": []}, evidence)
    if candidate is None:
        return None
    candidate["code_evidence"] = raw.get("code_evidence")
    candidate["setup_evidence"] = raw.get("setup_evidence")
    candidate = _ground_setup_evidence(_ground_code_evidence(candidate, evidence), history or {})
    # An implementation lesson must rest on real code; anything else is dropped.
    if not (isinstance(candidate.get("code_evidence"), dict) and candidate["code_evidence"].get("grounded")):
        return None
    # A missing control is a functional defect, not proof that a framework must change.
    if _framework_claim_needs_execution_evidence(candidate):
        return None
    # A lesson may add a companion requirement to guidance, but never tell the generator to ignore it.
    if re.search(r"\b(ignore|disregard|do not follow|don't follow|drop the guidance|discard)\b[^.]{0,60}\bguidance\b",
                 " ".join(str(candidate.get(f, "")) for f in ("preventative_action", "likely_cause_or_limitation")),
                 re.I):
        return None
    candidate = _drop_unsupported_persistence(llm, candidate, str(trajectory["task_request"]),
                                              _critique_evidence(evidence, appearance=False))
    if candidate is None:
        return None
    non_passed = {i for i, c in enumerate(checks) if isinstance(c, dict) and c.get("check") != "appearance"
                 and c.get("outcome") != "passed"} if isinstance(checks, list) else set()
    if not _shares_topic(_check_own_text(evidence, non_passed), candidate,
                         ("feature_object", "observed_result", "likely_cause_or_limitation")):
        return None
    candidate["feature_object"] = "[implementation] " + candidate["feature_object"]
    return candidate


QUESTION_FAILED_CHECK = """You are the developer who built this website. A tester tried to use one
feature and did not succeed. You are given the public requirement, the tester's steps and
answer, and your own source code. Answer in plain prose, 3-6 sentences, as if explaining
to a teammate who will build a similar website next week: what was the tester trying to
do and what happened; if you had to build this site again, what would you change in the
code so that the tester's steps succeed, and why did it fail (name the code that caused
it and quote one short line of it if you can see it); and state the lesson so that it
applies to any website with the same kind of feature, without this site's content. If the
failure is not caused by anything in the site (the tester simply ran out of steps, or it
expected something the requirement never mentions), say so plainly. Return JSON only:
{"answer": <your prose answer>}."""

QUESTION_APPEARANCE = """You are the developer who built this website. A reviewer looked at a screenshot
of its first screen and gave the feedback below. If you rebuilt the page, what ONE concrete
change would you make so that the reviewer would see what the requirement asks for (for
example a required feature that is not visible on the first screen, or a colour or layout
requirement that is not met)? Generic remarks (sparse, basic, not modern, add images or
cards, more polish) are stock wording, not lessons: if the feedback contains nothing more
specific, answer "nothing specific". Answer in 2-4 sentences. Return JSON only:
{"answer": <your prose answer>}."""

FORMAT_CASE_INSTRUCTIONS = """Turn a developer's plain answer into a structured lesson. Use only what the
answer says; add no new claims. If the answer says the failure was not caused by the
site, or it gives no usable lesson, return {"case": null}. Otherwise fill every field:
feature_object, user_trigger and expected_state_change describe the required behaviour of
one whole feature in requirement wording (what a user can do and what the page must then
show), never test-procedure wording; observed_result and likely_cause_or_limitation say
what happened and why; preventative_action is 1-2 sentences, a generalizable
implementation requirement for any website with the same kind of feature, without this
site's content, page names or example values; verification says how to check it;
transfer_limits says where it does not apply. If the answer quotes a line of code, set
code_evidence = {"file": <path as in code_files>, "snippet": <that line copied verbatim
from the file>}, else null. If the answer relies on wording that is written in the public
requirement, set requirement_evidence = {"quote": <verbatim phrase>, "site": <what the site
shows instead>}, else null. Return JSON only:
{"case":null|{"feature_object":str,"user_trigger":str,"expected_state_change":str,
"observed_result":str,"likely_cause_or_limitation":str,"preventative_action":str,
"verification":str,"transfer_limits":str,"code_evidence":null|{"file":str,"snippet":str},
"requirement_evidence":null|{"quote":str,"site":str}}}."""

FORMAT_APPEARANCE_INSTRUCTIONS = """Turn a developer's plain answer about a first-screen review into a
structured lesson. Use only what the answer says. If it says "nothing specific" or is
generic, return {"case": null}. Otherwise: observed_result and likely_cause_or_limitation
say what was not visible or not met and why; preventative_action is 1-2 sentences, a
design requirement about what the page must show, without this site's content;
verification says how to check it; transfer_limits says where it does not apply. Return
JSON only: {"case":null|{"observed_result":str,"likely_cause_or_limitation":str,
"preventative_action":str,"verification":str,"transfer_limits":str}}."""


def _check_evidence(evidence: list[dict], index: int) -> list[dict]:
    """Evidence for one functional check: its result, its GUI steps, and the site's code."""
    return [e for e in evidence if isinstance(e.get("ref"), dict) and (
        (e["ref"].get("kind") in ("evaluation_result", "gui_trajectory") and e["ref"].get("result_index") == index)
        or e["ref"].get("kind") in ("code_manifest", "code_file"))]


def create_reflection_by_questions(llm: Any, trajectory: Mapping[str, Any], evidence: list[dict],
                                   setup_history: dict | None = None) -> dict:
    """Question-style extraction: ask the developer a plain question per failed check (and one about
    the first screen), then format each answer into the same structured fields. Same output shape as
    create_reflection, and the same code/requirement grounding checks apply."""
    requirement = str(trajectory["task_request"])
    try:
        checks = json.loads(trajectory.get("evaluation_results") or "[]")
    except (TypeError, ValueError):
        checks = []
    code_files = [e for e in evidence if isinstance(e.get("ref"), dict) and e["ref"].get("kind") == "code_file"]
    functional, transcript = [], []
    for index, check in enumerate(checks):
        if not isinstance(check, dict) or check.get("check") == "appearance" or check.get("outcome") == "passed":
            continue
        scoped = _check_evidence(evidence, index)
        answer = str((llm.generate("reflection_question_failed_check", {
            "instructions": QUESTION_FAILED_CHECK, "public_requirement": requirement,
            "evidence": scoped}) or {}).get("answer", "")).strip()
        transcript.append({"check": check.get("check"), "question": "failed_check", "answer": answer})
        if not answer:
            continue
        formatted = llm.generate("reflection_format_case", {
            "instructions": FORMAT_CASE_INSTRUCTIONS, "public_requirement": requirement,
            "developer_answer": answer, "check_outcome": check.get("outcome"), "code_files": code_files})
        raw = formatted.get("case") if isinstance(formatted, dict) else None
        if not isinstance(raw, dict):
            continue
        refs = [e["ref"] for e in scoped if e["ref"].get("kind") in ("evaluation_result", "gui_trajectory")]
        item = _normalise_functional({**raw, "outcome": "failure" if check.get("outcome") == "failed" else "partial",
                                      "evidence_refs": refs}, evidence)
        if item is None:
            continue
        item["code_evidence"] = raw.get("code_evidence")
        item["requirement_evidence"] = raw.get("requirement_evidence")
        functional.append(_ground_requirement_evidence(_ground_code_evidence(item, evidence), requirement))
    appearance = None
    for index, check in enumerate(checks):
        if isinstance(check, dict) and check.get("check") == "appearance":
            answer = str((llm.generate("reflection_question_appearance", {
                "instructions": QUESTION_APPEARANCE, "public_requirement": requirement,
                "evidence": [e for e in evidence if isinstance(e.get("ref"), dict)
                             and e["ref"].get("kind") == "evaluation_result" and e["ref"].get("result_index") == index]})
                                or {}).get("answer", "")).strip()
            transcript.append({"check": "appearance", "question": "first_screen", "answer": answer})
            formatted = llm.generate("reflection_format_appearance", {
                "instructions": FORMAT_APPEARANCE_INSTRUCTIONS, "developer_answer": answer}) if answer else {}
            raw = formatted.get("case") if isinstance(formatted, dict) else None
            if isinstance(raw, dict):
                appearance = _normalise_appearance(
                    {**raw, "evidence_refs": [e["ref"] for e in evidence if isinstance(e.get("ref"), dict)
                                              and e["ref"].get("kind") == "evaluation_result"
                                              and e["ref"].get("result_index") == index]}, evidence)
    implementation = _implementation_case(llm, trajectory, evidence, checks, setup_history)
    reflections = ([appearance] if appearance is not None else []) + functional
    accepted = [item for item in reflections if item["accepted_for_memory"]]
    return {
        "reflection_id": uuid.uuid4().hex, "prompt_version": prompt_version(),
        "trajectory_id": str(trajectory["trajectory_id"]),
        "public_task_requirement": requirement, "task_summary": _task_summary(None),
        "appearance_reflection": appearance, "functional_reflections": functional,
        "implementation_reflection": implementation, "accepted_reflections": accepted,
        "reflections": reflections, "accepted_reflection_count": len(accepted),
        "raw_reflection_count": len(reflections), "dropped_by_critique": 0,
        "raw_model_output": {"style": "questions", "answers": transcript},
    }


def create_reflection(llm: Any, trajectory: Mapping[str, Any], evidence: list[dict],
                      *, review: bool = False, style: str = "structured",
                      setup_history: dict | None = None, appearance_mode: str = "single") -> dict:
    if style == "questions":
        return create_reflection_by_questions(llm, trajectory, evidence, setup_history=setup_history)
    reflection = _create_reflection_structured(llm, trajectory, evidence, review=review,
                                               setup_history=setup_history)
    has_code = any(isinstance(i.get("ref"), dict) and i["ref"].get("kind") == "code_file" for i in evidence)
    if appearance_mode == "grouped" and has_code:
        # The grouped path replaces the single appearance case (it needs the site's code as evidence).
        dropped: list = []
        cases = create_appearance_reflections(llm, trajectory, evidence, dropped)
        reflection["appearance_mode"] = "grouped"
        reflection["appearance_reflections"] = cases
        reflection["appearance_all_dropped"] = bool(dropped) and not cases
        reflection["appearance_dropped_no_citation"] = [
            {"deduction": c["deduction"], "preventative_action": c["preventative_action"],
             "code_evidence": c.get("code_evidence"), "problem": c.get("citation_problem")} for c in dropped]
        reflection["appearance_reflection"] = cases[0] if cases else None
        legacy = [i for i in reflection["reflections"] if i.get("channel") != "appearance"]
        reflection["reflections"] = cases + legacy
        reflection["accepted_reflections"] = [i for i in reflection["reflections"] if i["accepted_for_memory"]]
        reflection["accepted_reflection_count"] = len(reflection["accepted_reflections"])
        reflection["raw_reflection_count"] = len(reflection["reflections"])
    return reflection


def _create_reflection_structured(llm: Any, trajectory: Mapping[str, Any], evidence: list[dict],
                                  *, review: bool = False, setup_history: dict | None = None) -> dict:
    """Create a source-aware case archive without writing to the database."""
    result = llm.generate("post_task_reflection", {
        "instructions": REFLECTION_INSTRUCTIONS,
        "public_task_requirement": str(trajectory["task_request"]),
        "trajectory_id": str(trajectory["trajectory_id"]),
        "evaluation_results": trajectory.get("evaluation_results", ""),
        "evidence": evidence,
    })
    if not isinstance(result, dict):
        raise ValueError("Post-task reflection must return a JSON object")
    try:
        checks = json.loads(trajectory.get("evaluation_results") or "[]")
    except (TypeError, ValueError):
        checks = None
    # One call per failed/partial check, each seeing only that check's own evidence: a batched call
    # given several checks' trajectories at once had matched a case to the wrong check (it wrote about
    # whichever trajectory was most salient, not the one the outcome slot was for).
    functional = _functional_cases(llm, trajectory, evidence, checks)
    implementation = _implementation_case(llm, trajectory, evidence, checks, setup_history)
    appearance = _normalise_appearance(result.get("appearance_reflection"), evidence)
    # Review every case with a separate, single-purpose call; cases that rest on
    # unstated (hidden) expectations are dropped, weak causes/actions are rewritten.
    dropped = 0
    if review:
        reviewed_functional = []
        for item in functional:
            reviewed = _critique(llm, trajectory, evidence, item, _FUNCTIONAL_FIELDS, appearance=False)
            if reviewed is None:
                dropped += 1
            else:
                reviewed_functional.append(reviewed)
        functional = reviewed_functional
        if appearance is not None:
            appearance = _critique(llm, trajectory, evidence, appearance, _APPEARANCE_FIELDS, appearance=True)
            if appearance is None:
                dropped += 1
    reflections = ([appearance] if appearance is not None else []) + functional
    accepted = [item for item in reflections if item["accepted_for_memory"]]
    return {
        "reflection_id": uuid.uuid4().hex,
        "prompt_version": prompt_version(),
        "functional_skipped": list(LAST_FUNCTIONAL_SKIPS),
        "trajectory_id": str(trajectory["trajectory_id"]),
        "public_task_requirement": str(trajectory["task_request"]),
        "task_summary": _task_summary(result.get("task_summary")),
        "appearance_reflection": appearance,
        "functional_reflections": functional,
        "implementation_reflection": implementation,
        "accepted_reflections": accepted,
        # ``reflections`` is retained for old readers; it is now the complete
        # archived set, not only strict-provenance records.
        "reflections": reflections,
        "accepted_reflection_count": len(accepted),
        "raw_reflection_count": len(reflections),
        "dropped_by_critique": dropped,
        "raw_model_output": result,
    }


APPEARANCE_GROUPING_INSTRUCTIONS = """You group the reasons a screenshot reviewer gave for taking points off a
website. You get the reviewer's written analysis and grade (evaluation_result) of the website's
first-screen screenshot. If the grade is 5, return {"deductions": [], "groups": []}.

1) deductions: list every reason for taking points off, each as a verbatim phrase copied from
the analysis (general remarks such as "flat" or "lacks polish" count too; praise does not).
2) groups: put deductions in the same group ONLY when one and the same change to the website
would resolve all of them (test: if a developer followed the fix for one, would the others'
complaints also be resolved?). Reasons that need different changes stay in separate groups; when
unsure, keep them apart. Every deduction belongs to exactly one group. For each group give
"same_fix": one sentence naming the single change that resolves all its deductions.

Return JSON only:
{"deductions":[str],"groups":[{"deductions":[index into deductions],"same_fix":str}]}."""


APPEARANCE_CITATION_REPAIR_INSTRUCTIONS = """Each case below states a fact about a website's source code but its code citation could
not be verified (see "problem"). For every case give code_evidence = {"file": <path exactly as
supplied>, "snippet": <a verbatim excerpt of 1-6 lines copied character for character from that
file's supplied content>} that shows the fact in observed_result. Copy, never rephrase or
abbreviate, and do not use "..." inside the excerpt. If no excerpt in the supplied files shows
that fact, give null for that case.

Return JSON only: {"citations":[{"n":int,"code_evidence":null|{"file":str,"snippet":str}}]}."""


APPEARANCE_ONLY_INSTRUCTIONS = """You write appearance lessons for a website-generation memory
after the final locked evaluation. The website MUST NOT be repaired. You get the public
requirement, the screenshot reviewer's written analysis and grade (evaluation_result),
and the website's own source (code_manifest, code_file). Never repeat hidden answers.

The grade is out of 5. If the grade is 5, return {"appearance_reflections": []}.
Otherwise the reviewer named reasons for taking points off, already collected in "groups":
each group is a set of reasons that one and the same change resolves ("same_fix" says which).
Write EXACTLY ONE case per group, in order, and give its "group" index. Put what the code
shows for each reason of the group in observed_result (for example each count and each fact
as a separate sentence) and write preventative_action as ONE general rule that resolves the
whole group; the individual facts are examples of it, keep them. Do not merge groups and do
not split a group.

Stay with the reviewer's own words. preventative_action may only address what the reviewer
actually complained about. Do not add design remedies the reviewer did not name (images,
gradients, textures, animations, "modern flair") and do not describe what the screenshot
showed beyond what the reviewer wrote. If a general remark ("flat", "lacks polish") comes
with no concrete, checkable change that follows from the reviewer's words and the code, leave
that reason out instead of inventing a remedy.

The functional checks' results and the tester's GUI steps (evaluation_result and
gui_trajectory of the other checks) are supplied too. The reviewer saw only one first-screen
screenshot, so use those steps to test each deduction: if the tester actually reached and used
the thing the reviewer calls thin or missing, the real problem is that it is not visible on the
first screen (an appearance lesson about what must be shown up front), not that it is not
built; if the steps show the feature not responding or absent, it is a functional problem (see
routing). State which of the two the evidence supports in likely_cause_or_limitation.

[[TROUBLESHOOTING]] (Apply it to each deduction: what does the code show for it?)

Responsibility: a low grade is the website's responsibility. Never explain a deduction
by a screenshot or viewport limitation, and never conclude that the site is fine. If the
reviewer could not see something because it is below the first screen, the lesson is
that the required content must be visible without scrolling.

Use the source code to make each case concrete and checkable: count and quote what the
site actually contains (for example how many menu entries, whether a section has its own
content or is only a link label, whether any image is used). Put the finding in
observed_result. Give code_evidence = {"file": <path as supplied>, "snippet": <verbatim
1-6 lines from that file>} when a snippet shows it, otherwise null.

preventative_action: 1-2 sentences, a design requirement any OTHER similar website could
follow, with a checkable presence or "several" style test (for example "give every listed
menu category several entries, each with name, description and price"). Do not put this
site's business names, page names or counts in it (those belong in observed_result), and do
not use vague words such as "richer", "more modern" or "polished" on their own. verification: how to check it in the rendered page. transfer_limits: which
kinds of site it applies to.


Scope: every case is an APPEARANCE case (what the page shows and how it reads). Never write
a functional lesson here. If the steps show a feature not responding or absent, say so in
likely_cause_or_limitation (a functional problem is handled elsewhere) and still give the
visible-side lesson.

Citation and checkability: every case must carry code_evidence (a verbatim 1-6 line excerpt from
a supplied file that shows the fact the case rests on). preventative_action must contain a
countable or present/absent test that a developer can verify (for example "at least N entries",
"each section has its own heading and body text", "an image element is used"). If you cannot
provide both, leave that group out entirely instead of writing a vague case.

Facts: observed_result must state concrete facts taken from the supplied code and steps, not
only repeat the reviewer: for example how many entries a list has and what each contains, which
sections exist and what content each holds, which colours the stylesheet uses, whether an
image is used, and whether the tester reached and used the thing. Quote names or values as
they appear in the code. Only facts you can see in the supplied evidence; never guess.

Return JSON only:
{"appearance_reflections":[{"group":int,"observed_result":str,
"likely_cause_or_limitation":str,"preventative_action":str,"verification":str,
"transfer_limits":str,"code_evidence":null|{"file":str,"snippet":str},
"evidence_refs":[supplied refs]}]}."""


def create_appearance_reflections(llm: Any, trajectory: Mapping[str, Any], evidence: list[dict],
                                  dropped: list | None = None) -> list[dict]:
    """Appearance-only reflection: one case per reviewer deduction, grounded in the site's code.

    Independent of create_reflection (functional cases and the single-case appearance path
    are untouched). Writes nothing.
    """
    picked = []
    for item in evidence:
        ref, content = item.get("ref"), item.get("content")
        if isinstance(ref, dict) and ref.get("kind") in ("evaluation_result", "gui_trajectory", "evaluator_log",
                                                          "code_manifest", "code_file"):
            picked.append(item)
    if not any(i["ref"].get("kind") == "evaluation_result" and isinstance(i.get("content"), dict)
               and i["content"].get("check") == "appearance" for i in picked):
        return []
    norm = lambda text: re.sub(r"\s+", " ", str(text)).strip().lower()
    appearance_results = [i for i in picked if i["ref"].get("kind") == "evaluation_result"
                          and isinstance(i.get("content"), dict) and i["content"].get("check") == "appearance"]
    reviewer_text = " ".join(norm(i["content"].get("model_output", "")) for i in appearance_results)
    # Step 1: collect the deductions and group those that one change resolves. Code checks that every
    # phrase is really in the reviewer's text and that each belongs to exactly one group.
    grouping = llm.generate("post_task_appearance_grouping", {
        "instructions": APPEARANCE_GROUPING_INSTRUCTIONS, "evidence": appearance_results})
    phrases = [str(p).strip() for p in (grouping.get("deductions") or [])] if isinstance(grouping, dict) else []
    keep = {i for i, phrase in enumerate(phrases) if phrase and norm(phrase) in reviewer_text}
    groups, assigned = [], set()
    for group in (grouping.get("groups") or []) if isinstance(grouping, dict) else []:
        members = [i for i in (group.get("deductions") or []) if isinstance(i, int) and i in keep
                   and i not in assigned] if isinstance(group, dict) else []
        if members:
            assigned.update(members)
            groups.append({"deductions": [phrases[i] for i in members], "same_fix": str(group.get("same_fix", ""))})
    groups += [{"deductions": [phrases[i]], "same_fix": ""} for i in sorted(keep - assigned)]
    if not groups:
        return []
    # Step 2: one case per group.
    result = llm.generate("post_task_appearance_reflection", {
        "instructions": APPEARANCE_ONLY_INSTRUCTIONS,
        "public_task_requirement": str(trajectory["task_request"]),
        "groups": groups,
        "evidence": picked,
    })
    raw = result.get("appearance_reflections") if isinstance(result, dict) else None
    if not isinstance(raw, list):
        return []
    code_files = {e["ref"]["path"] for e in evidence
                  if isinstance(e.get("ref"), dict) and e["ref"].get("kind") == "code_file"}

    def build(item: dict, index: int, claim: object) -> dict | None:
        case = _normalise_appearance(item, evidence)
        if case is None:
            return None
        case["deduction"] = item["deduction"]
        case["group_reason"] = groups[index]["same_fix"]
        case["deduction_grounded"] = all(norm(part) in reviewer_text for part in groups[index]["deductions"])
        case["code_evidence"] = claim
        case = _ground_code_evidence(case, evidence)
        case["evidence_refs"] = [
            *case.get("evidence_refs", []),
            {"kind": "reviewer_deduction", "quote": case["deduction"][:600],
             "grounded": case["deduction_grounded"]},
            {"kind": "grouping", "same_fix": case["group_reason"][:300]}]
        return case

    cases, failed = [], []
    for item in raw:
        index = item.get("group") if isinstance(item, dict) else None
        if not _complete(item, _APPEARANCE_FIELDS) or not isinstance(index, int) or not 0 <= index < len(groups):
            continue
        item = {**item, "deduction": " || ".join(groups[index]["deductions"])}
        case = build(item, index, item.get("code_evidence"))
        if case is None:
            continue
        (cases if (case["code_evidence"] or {}).get("grounded") else failed).append((item, index, case))
    cases = [case for _, _, case in cases]
    # One repair round: the model may have given no excerpt, or one that is not verbatim in the file.
    # The code re-checks the new excerpt exactly as before; the model's word is never enough.
    if failed:
        problems = []
        for number, (item, _, case) in enumerate(failed):
            claim = case["code_evidence"] or {}
            if not claim.get("snippet"):
                problem = "no code excerpt was given"
            elif claim.get("file") not in code_files:
                problem = "the file is not one of the supplied files: " + str(claim.get("file"))
            else:
                problem = "the excerpt does not appear verbatim in " + str(claim.get("file"))
            problems.append({"n": number, "observed_result": case["observed_result"],
                             "previous_file": claim.get("file"), "previous_excerpt": claim.get("snippet"),
                             "problem": problem})
        try:
            repair = llm.generate("post_task_appearance_citation_repair", {
                "instructions": APPEARANCE_CITATION_REPAIR_INSTRUCTIONS, "cases": problems,
                "evidence": [i for i in picked if i["ref"].get("kind") in ("code_manifest", "code_file")]})
        except ValueError:
            repair = {}
        fixes = {c.get("n"): c.get("code_evidence") for c in (repair.get("citations") or [])
                 if isinstance(c, dict)} if isinstance(repair, dict) else {}
        for number, (item, index, previous) in enumerate(failed):
            case = build(item, index, fixes.get(number)) if fixes.get(number) else None
            if case is not None and (case["code_evidence"] or {}).get("grounded"):
                case["citation_repaired"] = True
                cases.append(case)
            else:
                previous["citation_problem"] = problems[number]["problem"]
                if dropped is not None:
                    dropped.append(previous)
    return cases


def append_reflection(path: Path, reflection: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(_json(dict(reflection)) + "\n")


def reflective_evidence_loader(base_loader: Callable[[dict], list[dict]],
                               artifact_path: Path) -> Callable[[dict], list[dict]]:
    """Attach the complete case archive as secondary, provenance-linked evidence."""
    def load(trajectory: dict) -> list[dict]:
        evidence = list(base_loader(trajectory))
        if not artifact_path.is_file():
            return evidence
        selected = None
        for line in artifact_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                event = json.loads(line)
                if event.get("trajectory_id") == trajectory["trajectory_id"]:
                    selected = event
        if selected:
            evidence.append({
                "ref": {"kind": "post_task_case", "reflection_id": selected["reflection_id"]},
                "content": selected,
            })
        return evidence
    return load


for _name in ("REFLECTION_INSTRUCTIONS", "IMPLEMENTATION_INSTRUCTIONS", "APPEARANCE_ONLY_INSTRUCTIONS"):
    globals()[_name] = globals()[_name].replace("[[TROUBLESHOOTING]]", TROUBLESHOOTING_STEPS)


def prompt_version() -> str:
    """Short fingerprint of every reflection instruction in this module, so each stored reflection
    records which prompt version wrote it (prompts change between runs; see the regression set)."""
    import hashlib
    texts = [f"{name}={value}" for name, value in sorted(globals().items())
             if name.endswith("_INSTRUCTIONS") and isinstance(value, str)]
    return hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()[:12]
