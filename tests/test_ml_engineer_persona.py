from cancer_claw.agent.engine.persona import list_personas, load_persona


def test_ml_engineer_persona_is_train_partner():
    p = load_persona("ml_engineer")
    assert p.id == "ml_engineer"
    assert p.name == "模型训练工程师"
    assert "train_run" in p.description
    assert "train_run" in p.soul_text
    assert "training.python" in p.soul_text
    assert "DESIGN.json" in p.soul_text
    assert "模型训练页" not in p.soul_text
    ids = {x.id for x in list_personas()}
    assert "ml_engineer" in ids
    assert "master" in ids
