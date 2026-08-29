from __future__ import annotations

from models import NormalizedItem, business_extra


def _item(**kwargs) -> NormalizedItem:
    base = dict(
        item_type="answer",
        zhihu_id="456",
        url="https://www.zhihu.com/answer/456",
        title="t",
        parent_id="123",
    )
    base.update(kwargs)
    return NormalizedItem(**base)


def test_business_extra_answer():
    extra = business_extra(_item())
    assert extra == {"answer_id": "456", "question_id": "123", "parent_id": "123"}


def test_business_extra_article_with_column():
    extra = business_extra(
        _item(item_type="article", zhihu_id="789", parent_id="col1", url="https://zhuanlan.zhihu.com/p/789")
    )
    assert extra == {"article_id": "789", "column_id": "col1", "parent_id": "col1"}


def test_business_extra_article_without_column():
    extra = business_extra(
        _item(item_type="article", zhihu_id="789", parent_id=None, url="https://zhuanlan.zhihu.com/p/789")
    )
    assert extra == {"article_id": "789"}


def test_business_extra_pin():
    extra = business_extra(_item(item_type="pin", zhihu_id="1", parent_id=None, url="https://www.zhihu.com/pin/1"))
    assert extra == {"pin_id": "1"}


def test_business_extra_question():
    extra = business_extra(
        _item(item_type="question", zhihu_id="9", parent_id=None, url="https://www.zhihu.com/question/9")
    )
    assert extra == {"question_id": "9"}
