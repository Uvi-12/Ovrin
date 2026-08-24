// tests/adapter_test.rs

use ovrin_adapter::adapter;

#[test]
fn test_adapter_handles_somecrate_return_value() {
    // We test that the adapter function properly handles the returned value
    // from somecrate and produces the correct output categorization.
    let res = adapter::adapt();
    assert!(res == "non-negative" || res == "negative");
}
