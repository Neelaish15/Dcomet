from src.agents.logic_agents import DSOAgent


def test_dso_rejects_overloaded_line():
    dso = DSOAgent("dso_test", max_line_loading_pct=80.0)
    dso.update_grid_state(voltage_pu=1.0, frequency_hz=50.0, line_loading_pct=79.5)

    result = dso.validate_trade("consumption", quantity_w=20.0, consumer_id="consumer_1")
    assert result["approved"] is False
    assert "would_exceed_loading" in result["constraints_violated"]


def test_dso_accepts_safe_trade():
    dso = DSOAgent("dso_test", max_line_loading_pct=80.0)
    dso.update_grid_state(voltage_pu=1.0, frequency_hz=50.0, line_loading_pct=10.0)

    result = dso.validate_trade("consumption", quantity_w=5.0, consumer_id="consumer_1")
    assert result["approved"] is True
