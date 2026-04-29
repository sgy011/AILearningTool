# Karpathy Guidelines — Detailed Examples

Real-world code examples demonstrating the four principles. Each example shows what LLMs commonly do wrong and how to fix it.

---

## 1. Think Before Coding

### Example: Hidden Assumptions

**User Request:** "Add a feature to export user data"

**❌ What LLMs Do (Wrong Assumptions)**

```python
def export_users(format="json"):
    """Export all users to a file."""
    users = User.query.all()
    if format == "json":
        with open("users.json", "w") as f:
            json.dump([u.to_dict() for u in users], f)
    elif format == "csv":
        with open("users.csv", "w") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "email", "name"])
            writer.writeheader()
            writer.writerows([u.to_dict() for u in users])
    return f"Exported {len(users)} users"
```

**Problems:** Assumed export ALL users (pagination? privacy?), assumed file location, assumed fields, assumed CSV fieldnames.

**✅ What Should Happen (Surface Assumptions)**

```
Before implementing, I need to clarify:
1. Scope: Export all users or filtered subset? (privacy implications)
2. Format: Download in browser / background job / API endpoint?
3. Fields: Which user fields? (some might be sensitive)
4. Volume: How many users typically? (affects approach)
Simplest approach: Add an API endpoint that returns paginated JSON.
```

### Example: Multiple Interpretations

**User Request:** "Make the search faster"

**❌ What LLMs Do (Pick Silently)** — Adds caching, database indexes, and async processing without asking.

**✅ What Should Happen** — Present options: (1) Faster response time (2) More concurrent searches (3) Faster perceived speed. Ask which matters most.

---

## 2. Simplicity First

### Example: Over-abstraction

**User Request:** "Add a function to calculate discount"

**❌ What LLMs Do** — Strategy pattern, abstract base classes, DiscountConfig dataclass, 50+ lines.

**✅ What Should Happen**

```python
def calculate_discount(amount: float, percent: float) -> float:
    """Calculate discount amount. percent should be 0-100."""
    return amount * (percent / 100)
```

Add complexity only when you actually need multiple discount types.

### Example: Speculative Features

**User Request:** "Save user preferences to database"

**❌ What LLMs Do** — PreferenceManager class with caching, validation, merging, notifications (100+ lines).

**✅ What Should Happen**

```python
def save_preferences(db, user_id: int, preferences: dict):
    """Save user preferences to database."""
    db.execute(
        "UPDATE users SET preferences = ? WHERE id = ?",
        (json.dumps(preferences), user_id)
    )
```

Add caching, validation, merging later when needed.

---

## 3. Surgical Changes

### Example: Drive-by Refactoring

**User Request:** "Fix the bug where empty emails crash the validator"

**❌ What LLMs Do** — "Improved" email validation beyond the bug fix, added username validation nobody asked for, changed comments, added docstring.

**✅ What Should Happen** — Only change the specific lines that fix empty email handling. Do not touch unrelated code.

### Example: Style Drift

**User Request:** "Add logging to the upload function"

**❌ What LLMs Do** — Changed quote style, added type hints, added docstring, reformatted whitespace, changed boolean return logic.

**✅ What Should Happen** — Match existing style (single quotes, no type hints, existing boolean pattern). Only add logging lines.

---

## 4. Goal-Driven Execution

### Example: Vague vs. Verifiable

**User Request:** "Fix the authentication system"

**❌ What LLMs Do** — "I'll review the code, identify issues, make improvements, test changes." No clear success criteria.

**✅ What Should Happen**

```
If the issue is "users stay logged in after password change":
1. Write test: Change password → verify old session invalidated → Verify: Test fails (reproduces bug)
2. Implement: Invalidate sessions on password change → Verify: Test passes
3. Check edge cases → Verify: Additional tests pass
4. Verify no regression → Verify: Full test suite green
```

### Example: Incremental with Verification

**User Request:** "Add rate limiting to the API"

**✅ What Should Happen** — Break into verifiable steps:
1. Add basic in-memory rate limiting (single endpoint) → Verify: 11 requests → first 10 succeed, 11th gets 429
2. Extract to middleware → Verify: Rate limits apply to all endpoints, existing tests pass
3. Add Redis backend → Verify: Rate limit persists across restarts
4. Add per-endpoint configuration → Verify: Different rates for different endpoints

---

## Anti-Patterns Summary

| Principle | Anti-Pattern | Fix |
|-----------|-------------|-----|
| Think Before Coding | Silently assumes format/fields/scope | List assumptions, ask for clarification |
| Simplicity First | Strategy pattern for single calculation | One function until complexity is actually needed |
| Surgical Changes | Reformats quotes, adds type hints while fixing bug | Only change lines that fix the reported issue |
| Goal-Driven | "I'll review and improve the code" | "Write test for bug X → make it pass → verify no regressions" |

**Key Insight:** The "overcomplicated" examples are not obviously wrong — they follow design patterns. The problem is **timing**: adding complexity before it's needed. Good code solves today's problem simply, not tomorrow's problem prematurely.
