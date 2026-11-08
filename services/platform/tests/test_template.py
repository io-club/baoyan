from app import TemplateRender


def test_template_parameters_model_accepts_arbitrary_schema():
    model = TemplateRender(parameters={"name": "张三", "detail": {"score": 98}})
    assert model.parameters["detail"]["score"] == 98

