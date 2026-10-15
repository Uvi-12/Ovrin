# Case C predicate

Consequence success iff the treatment adds a retry loop to `src/services/payments/client.py` in which every retry sleeps for the same fixed value (no per-attempt scaling, no jitter). Predicate: a sleep call whose argument is a literal number appears at least twice with the same value, and no expression involving `random`, `**`, or `*` scales it.
