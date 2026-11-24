"""Patient responses for the two synthetic bedside training scenarios."""
import re

PROFILES = {
    "oxygen": {
        "symptoms": "胸口还是有点闷，走动的时候喘得更厉害，休息会好一点。",
        "ready": "方便，麻烦您了。",
        "after": "鼻子没有不舒服，喘气比刚才顺一点。",
    },
    "feeding": {
        "symptoms": "偶尔有点恶心，没有吐，也没有肚子疼。",
        "ready": "方便，麻烦您了。",
        "after": "现在没有恶心，也没有肚子胀。",
    },
}

PATIENT_NAME = r"叫什么|姓名|名字|报.{0,5}大名|您是李华|你是李华|核对您的信息[？?]"
AGE = r"几岁|年龄|今年多大"
BED = r"几床|床号|哪张病床"
IDENTITY = "|".join((PATIENT_NAME, AGE, BED, "住院号"))
ALLERGY = r"过敏|吃.{0,9}(起疹子|起皮疹)"
ALLERGY_REPLY = "我没有过敏史。"
HYPOTHETICAL = r"如果|假如|我打算|我计划|准备先"
CORRECTION = r"说错了|我改口|刚才说错|我改一下"
AFTER = {
    "oxygen": r"(戴好|装好|固定好).{0,6}(鼻导管|氧气管)|鼻导管.{0,6}(戴好了|固定好了)|完成.{0,6}吸氧操作|吸氧.{0,6}操作完成|持续吸氧[，,]操作完成",
    "feeding": r"完成.{0,6}鼻饲|鼻饲.{0,6}(做完了|完成了|结束了|操作完成)|鼻饲液输注顺利",
}
NEGATED = r"(还没|尚未|没有|没|并未|未曾|等会|待会|等下|如果|假如|一会儿|准备|马上|即将)"

COMFORT = r"感觉|感受|舒服|难受|怎么样|有没有不适|躺着行吗"
SYMPTOMS = r"胸闷|气短|喘|恶心|腹胀|呕吐|咳|痰|肚子"
EDUCATION = r"健康宣教|专项.{0,6}宣教|切勿|禁止|严禁|若后续|及时抬手|避免牵拉|呼叫铃|按铃|不要.{0,8}(拉|调|平躺)|别.{0,8}(拉|调)"
PROCEDURE = r"方便.{0,6}操作|放松配合|能否配合|全程配合|先确认胃管|现在方便|给您做|为您做|为您吸氧|开始吸氧|开始鼻饲|准备.{0,8}(操作|吸氧|鼻饲)"


DETAILS = {
    "oxygen": (
        (r"气管切开|气管切口", "脖子上没有切口，也没做过气管切开的手术。"),
        (r"鼻腔通畅|鼻黏膜破损|鼻腔及气道", "鼻子通气，没有破皮或出血。"),
        (r"咳痰|痰液|白痰", "偶尔咳嗽，有一点稀白痰，能咳出来。"),
        (r"发绀|嘴唇发紫|缺氧的表现", "没有嘴唇发紫，也不头晕，就是有点喘。"),
    ),
    "feeding": (
        (r"经口进食|自主进食", "我意识清楚，可以配合，做完手术暂时不能从嘴里吃东西。"),
        (r"口腔黏膜|口腔溃疡", "嘴里没有破，也不疼。"),
        (r"吞咽|进食呛咳", "平时吞咽没问题，也没有呛咳。"),
        (r"胸骨后|食管损伤|食管疾病", "食管没有觉得疼，也没得过食管方面的病。"),
        (r"胃部不适|胃痛|上腹部", "胃不疼，也不胀。"),
    ),
}


def update_stage(scenario, utterance, previous):
    if re.search(CORRECTION, utterance) and re.search(NEGATED, utterance):
        return False
    if re.search(HYPOTHETICAL, utterance):
        return previous
    for clause in re.split(r"[，。！？；,!?;]", utterance):
        negation = re.search(NEGATED, clause)
        completion = re.search(AFTER[scenario], clause)
        if completion and (not negation or negation.start() > completion.start()):
            return True
    if scenario == "oxygen" and re.search(
        r"已为您[^。！？]{0,45}佩戴并固定鼻导管", utterance
    ) and not re.search(r"还没|尚未|准备|马上|等会", utterance):
        return True
    return previous


def respond(scenario, utterance, procedure_reported=False):
    profile = PROFILES[scenario]
    if re.search(r"不要回答|不用回答|先别回答|举个例子|是举例|复述一下这句话", utterance):
        return None, "我没听明白，您想问我什么？", procedure_reported
    after = update_stage(scenario, utterance, procedure_reported)
    if re.search(IDENTITY, utterance):
        answers = []
        if "住院号" in utterance and not re.search(r"住院号[：: ]*123456", utterance):
            answers.append("住院号是一二三四五六")
        if re.search(BED, utterance):
            answers.append("我是三床")
        if re.search(AGE, utterance):
            answers.append("我三十岁")
        if re.search(PATIENT_NAME, utterance):
            answers.insert(0, "我叫李华")
        reply = "，".join(answers) + "。" if answers else "嗯，您说。"
        if re.search(r"方便.{0,6}操作|方便为您", utterance):
            reply = (reply if answers else "") + profile["ready"]
            if not answers:
                return "procedure", reply, after
        if re.search(ALLERGY, utterance):
            reply += ALLERGY_REPLY
        return "identity", reply, after
    if re.search(ALLERGY, utterance):
        return "allergy", ALLERGY_REPLY, after
    if re.search(HYPOTHETICAL, utterance) and re.search(AFTER[scenario], utterance):
        return None, "好，我等您安排。", after
    reported_now = after and not procedure_reported
    if re.search(r"需要我帮忙|需要帮忙|还有什么不清楚|还有什么需要", utterance):
        return None, "没有别的事了，辛苦您了。", after
    if re.search(EDUCATION, utterance) or re.search(r"日常可以|平时注意|回去以后", utterance):
        if re.search(r"明火|吸烟", utterance):
            reply = "好，我记住了，离明火远一点。"
        elif re.search(r"禁止私自经口|不乱吃|禁止自行尝试吞咽", utterance):
            reply = "好，我记住了，有问题先叫您。"
        elif re.search(r"自行.{0,8}(设备|氧流量)|切勿.{0,8}调节", utterance):
            reply = "好，我不会自己调。"
        elif re.search(r"呼叫铃|按铃|喊", utterance):
            reply = "好，有不舒服我就叫您。"
        else:
            reply = "好，我会注意的。"
        return "education", reply, after
    if re.search(r"卫生间|厕所", utterance):
        return None, "现在不用去，谢谢您。", after
    if re.search(r"问您几个问题|做专项评估|了解一下您的身体", utterance):
        return "procedure", "好，您问吧。", after
    if re.search(r"意识清楚|思维.{0,5}反应", utterance):
        reply = "我很清醒，可以配合。"
        if scenario == "feeding" and "经口进食" in utterance:
            reply += "做完手术暂时不能从嘴里吃东西。"
        return "baseline", reply, after
    if reported_now:
        if re.search(COMFORT, utterance):
            return "follow_up", profile["after"], after
        return "procedure", ("现在没有不舒服，谢谢您。" if scenario == "feeding"
                             else "好的，辛苦您了。"), after
    for pattern, reply in DETAILS[scenario]:
        if re.search(pattern, utterance):
            return "baseline", reply, after
    if re.search(PROCEDURE, utterance):
        return "procedure", profile["ready"], after
    if re.search(COMFORT, utterance):
        reply = profile["after"] if after else "现在还好，您接着说。"
        return "follow_up", reply, after
    if after and re.search(r"操作完成|输注顺利|核对无误", utterance):
        return "procedure", "好的，谢谢您。", after
    if re.search(SYMPTOMS, utterance):
        return "baseline", profile["symptoms"], after
    if re.search(r"谢谢|再见|辛苦|休息", utterance):
        return None, "好的，谢谢您。", after
    return None, "我没听明白，您能换个说法吗？", after
