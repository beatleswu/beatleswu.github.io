"""Candidate G065 policy. No corpus writes and no inference from Go strength.

Only the opt-in g065-explicit-v1 dialect treats exact C[G065:CORRECT] /
C[G065:INCORRECT] as verdicts. TE/BM/RE and natural language comments are
preserved by the parser, but are not a portable puzzle correctness standard.
Unannotated linear legacy trees retain compatibility; ambiguous trees require
curation, not an automatic incorrect grade.
"""


class AnswerAuthorityUnavailable(ValueError):
    pass


def terminal_verdict(question, root, terminal):
    if question.get('answer_policy') == 'g065-explicit-v1':
        # A failure anywhere on this branch dominates a later success marker.
        current, correct = terminal, False
        while current is not None:
            comment = current.metadata.get('comment', '').strip()
            if comment == 'G065:INCORRECT':
                return False
            # Success must mark the terminal, never just a promising first move.
            if current is terminal and comment == 'G065:CORRECT':
                correct = True
            current = current.parent
        if correct:
            return True
        raise AnswerAuthorityUnavailable('unmarked_terminal_requires_owner_review')
    if question.get('answer_policy'):
        raise AnswerAuthorityUnavailable('unsupported_answer_policy')
    pending = [root]
    while pending:
        node = pending.pop()
        # Do not reinterpret annotations or branch order as an implicit answer.
        props = node.metadata.get('properties', {})
        if len(node.children) > 1 or any(k in props for k in ('C', 'TE', 'BM', 'DO', 'IT')):
            raise AnswerAuthorityUnavailable('legacy_ambiguous_requires_owner_review')
        pending.extend(node.children)
    return True
