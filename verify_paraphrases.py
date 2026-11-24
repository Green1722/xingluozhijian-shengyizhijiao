"""Synthetic paraphrases independent of the two Word scripts."""
import argparse
import csv
from pathlib import Path

from patient import respond


CASES = (
    ("oxygen", False, "麻烦报一下您的大名", "identity", "李华", False),
    ("feeding", False, "方便说一下您今年多大吗", "identity", "三十岁", False),
    ("oxygen", False, "您躺的是哪张病床", "identity", "三床", False),
    ("feeding", False, "吃什么东西会起疹子吗", "allergy", "没有过敏", False),
    ("oxygen", False, "先别回答过敏的事", None, "", False),
    ("feeding", False, "老师刚才说「鼻饲已经完成」是举例", None, "", False),
    ("oxygen", False, "如果顺利，我就给您戴好鼻导管", None, "", False),
    ("oxygen", False, "我打算先戴好鼻导管", None, "", False),
    ("feeding", False, "鼻饲还没做完呢", None, "", False),
    ("feeding", True, "我改一下，刚刚还没完成鼻饲", None, "", False),
    ("oxygen", True, "我说错了，鼻导管还没固定好", None, "", False),
    ("oxygen", True, "没带您的眼镜，但已经戴好鼻导管", None, "", True),
    ("oxygen", False, "没带您的眼镜，但已经戴好鼻导管", "procedure", "", True),
    ("feeding", False, "这回鼻饲做完了，您有没有觉得难受", "follow_up", "没有恶心", True),
    ("oxygen", False, "已经戴好鼻导管，您叫什么名字", "identity", "李华", True),
    ("feeding", False, "您叫什么名字，有没有过敏史", "identity", "没有过敏", False),
    ("oxygen", False, "谢谢您配合，我们接着做", None, "", False),
    ("feeding", False, "明天会下雨吗", None, "", False),
)


HOLDOUT = (
    ("feeding", False, "您今年多大，在哪张病床", "identity", "三床", False),
    ("oxygen", False, "准备先帮您固定好鼻导管", None, "", False),
    ("feeding", False, "鼻饲结束了，您感觉好点吗", "follow_up", "没有恶心", True),
    ("oxygen", True, "我重说一遍，鼻导管其实还没固定好", None, "", False),
    ("oxygen", False, "能告诉我您的全名吗", "identity", "李华", False),
    ("feeding", False, "先不用回答，我们只是假设已经完成鼻饲", None, "", False),
    ("feeding", False, "您好，查一下住院号，哪些东西会让您起皮疹", "identity", "一二三四五六", False),
    ("oxygen", False, "氧气管我已经帮您固定好了", "procedure", "", True),
)


def run(output, cases):
    failures = 0
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("case", "before", "nurse", "expected_marker", "expected_phrase",
                         "expected_after", "observed_marker", "observed_reply", "observed_after", "result"))
        for scenario, before, line, marker, phrase, after in cases:
            actual_marker, reply, actual_after = respond(scenario, line, before)
            passed = (actual_marker, actual_after) == (marker, after) and phrase in reply
            failures += not passed
            writer.writerow((scenario, before, line, marker, phrase, after, actual_marker, reply,
                             actual_after, "PASS" if passed else "FAIL"))
    print(f"{len(cases) - failures}/{len(cases)} passed; {failures} failed")
    return failures


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("output", type=Path)
    cli.add_argument("--holdout", action="store_true")
    args = cli.parse_args()
    sys_exit = run(args.output, HOLDOUT if args.holdout else CASES)
    raise SystemExit(bool(sys_exit))
