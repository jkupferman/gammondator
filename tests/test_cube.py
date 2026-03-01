from app.cube import _map_proper_action


def test_map_proper_action_for_double_context() -> None:
    assert _map_proper_action("Double, take", "double") == "double"
    assert _map_proper_action("No double, beaver (25.8%)", "double") == "nodouble"


def test_map_proper_action_for_take_pass_context() -> None:
    assert _map_proper_action("Double, pass", "take") == "pass"
    assert _map_proper_action("Double, take", "pass") == "take"
    assert _map_proper_action("No double", "take") == "take"
