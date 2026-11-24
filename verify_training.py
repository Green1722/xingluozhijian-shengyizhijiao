from patient import respond

for case, performed, pending in (
    ("oxygen", "已经戴好鼻导管", "还没有戴好鼻导管"),
    ("feeding", "已经完成鼻饲", "还没有完成鼻饲"),
):
    marker, reply, stage = respond(case, "请问您的姓名和住院号")
    assert marker == "identity" and "李华" in reply and "一二三四五六" in reply
    assert respond(case, "只是举个例子，有没有过敏史")[0] is None
    assert respond(case, pending)[2] is False
    assert respond(case, performed)[2] is True
    assert respond(case, "我刚才说错了，" + pending, True)[2] is False
    assert respond(case, "现在有什么感觉", True)[1] != respond(case, "现在有什么感觉", False)[1]
    assert respond(case, "谢谢您的配合")[0] is None
    print(case, "7 checks OK")
