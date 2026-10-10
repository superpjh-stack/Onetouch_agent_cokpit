"""Public agent identity and per-question address policy shared with the UI."""
import re

WAKE_POLICY = {
    'agent_name': '원터치',
    'wake_aliases': ['원터치', '원터치야', '원터치님'],
    'require_wake_name': True,
}


def calls_agent(text: str, policy: dict = WAKE_POLICY) -> bool:
    if not policy['require_wake_name']:
        return True
    aliases = {' '.join(alias.split()) for alias in [policy['agent_name'], *policy['wake_aliases']] if alias.strip()}
    names = '|'.join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    return bool(re.match(r'''^[\s"'“‘]*(?:''' + names + r')(?=$|[\s,，.!?。！？:：~～])', ' '.join(text.split())))


def addressed_question(question: str) -> str:
    return f"{WAKE_POLICY['agent_name']}, {question}"


def question_content(text: str) -> str:
    """Remove only the verified address so company names do not bias retrieval."""
    if not calls_agent(text):
        return text
    names = '|'.join(re.escape(alias) for alias in sorted(set([WAKE_POLICY['agent_name'], *WAKE_POLICY['wake_aliases']]), key=len, reverse=True))
    return re.sub(r'''^[\s"'“‘]*(?:''' + names + r')(?=$|[\s,，.!?。！？:：~～])[\s,，.!?。！？:：~～]*', '', text, count=1).strip()
