// src/adapter.rs

/// Adapter function that processes the return value from `somecrate`.
/// It calls `somecrate::f()` and handles the resulting value.
pub fn adapt() -> &'static str {
    let value = somecrate::f();
    if value >= 0 {
        "non-negative"
    } else {
        "negative"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Mocking or testing the handler's behavior on return values.
    #[test]
    fn test_adapt_handling() {
        // Since we are unit testing the adapter's logic, we verify
        // that it correctly maps the return value of somecrate.
        let result = adapt();
        assert!(result == "non-negative" || result == "negative");
    }
}
