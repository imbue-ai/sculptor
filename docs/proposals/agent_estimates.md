# Enable agents to surface estimated cost, time to completion, etc

It would be nice to add this to `sculptor/sculptor/interfaces/agents/v1/agent.py`

```python
class AgentCompletionEstimate(SerializableModel):
    """
    An estimate of the agent's completion status, including time, cost, and probability of success.
    """

    # estimated remaining time to complete the task, in seconds
    remaining_time_in_seconds: float | None = None
    # estimated remaining cost to complete the task, in monetary units
    remaining_cost_in_dollars: float | None = None
    # estimated probability of successful completion, on a scale from 0.0 to 1.0
    probability_of_completion: Probability = Probability(1.0)
    # Fraction of the overall estimated work that is complete so far
    done: NormalizedScore = NormalizedScore(1.0)

```

Reasoning:
- This information would be *really* nice to see from the task overview screen, and we could probably create it fairly easily.
