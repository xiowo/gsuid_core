"""软触发沉默门规则预筛：零 LLM 路径。"""

from gsuid_core.ai_core.heartbeat.decision import _normalize_speak_decision, _reactive_gate_rule_prefilter


def test_empty_and_pure_particles_silence() -> None:
    assert _reactive_gate_rule_prefilter("") is False
    assert _reactive_gate_rule_prefilter("哈哈哈") is False
    assert _reactive_gate_rule_prefilter("嗯…") is False
    assert _reactive_gate_rule_prefilter("！！！") is False


def test_short_followup_passes() -> None:
    # 包含确切疑问/动作词（怎么样/改成）直接放行
    assert _reactive_gate_rule_prefilter("你说的那个怎么样了") is True
    assert _reactive_gate_rule_prefilter("改成明天八点") is True
    assert _reactive_gate_rule_prefilter("角色甲还在吗", persona_name="角色甲") is True
    assert _reactive_gate_rule_prefilter("角色甲还在吗") is None


def test_ambiguous_goes_to_llm() -> None:
    # P0-7: 剔除纯高频词（你/那个/然后），没有确切跟进动作时不走规则直通，交给 LLM 门
    assert _reactive_gate_rule_prefilter("你刚才发的那个") is None
    assert _reactive_gate_rule_prefilter("然后还有呢") is None
    assert _reactive_gate_rule_prefilter("今天群里好热闹啊感觉大家都挺有精神的") is None


def test_decision_typo_and_negation_normalization() -> None:
    dec1 = _normalize_speak_decision({"should_speck": True, "mood": "calm"})
    assert dec1 is not None and dec1.get("should_speak") is True

    dec2 = _normalize_speak_decision({"should_not_speak": True, "mood": "calm"})
    assert dec2 is not None and dec2.get("should_speak") is False

    dec3 = _normalize_speak_decision({"should_not_speak": False, "mood": "calm"})
    assert dec3 is not None and dec3.get("should_speak") is True

    dec4 = _normalize_speak_decision({"dont_speak": True, "mood": "calm"})
    assert dec4 is not None and dec4.get("should_speak") is False

    dec5 = _normalize_speak_decision([{"shoud_speak": True}])
    assert dec5 is not None and dec5.get("should_speak") is True
