# Enable agents to ask questions to the user

It would be nice to add this to `sculptor/sculptor/interfaces/agents/v1/agent.py`

```python
class UserQuestion(SerializableModel):
    """
    A question that the agent has for the user.

    This is used to gather information that the agent needs to proceed with its task.

    Once it is answered, the `answer` field should be filled in with the user's response.
    """

    # a short (single-line) description of the question. Should end with a question mark!
    question: str
    # the answer from the user, if any
    answer: str | None = None
    # how "blocking" this question is, on a scale from 0.0 to 1.0
    blocking: NormalizedScore = NormalizedScore(1.0)
    # how important this question is, on a scale from 0.0 to 1.0
    importance: NormalizedScore = NormalizedScore(1.0)

```

Reasoning:
- This allows agents to ask questions to the user, which is essential for gathering information that the agent needs to proceed with its task.
- This interface allows those questions to be async, and for us to understand how important they are (eg, are they worth surfaceing to the user immediately)
