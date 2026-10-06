from sentinel_core.state import get_log_paths


def test_regression_log_names_do_not_collide() -> None:
	assert get_log_paths("a.b") != get_log_paths("a_b")
	assert get_log_paths("a/b") != get_log_paths("a%2Fb")
