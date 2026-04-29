"""向 AI 社区数据库插入 100 条测试帖子，每条附带 5 条评论。"""
from __future__ import annotations

import random
import time
from pathlib import Path

from utils.community_db import (
    CATEGORIES,
    _conn,
    init_community_db,
)

# ── 测试用户池 ──
USERS = [
    (1, "AI探索者"), (2, "深度学习者"), (3, "数据科学家"), (4, "算法工程师"),
    (5, "模型训练师"), (6, "CV研究员"), (7, "NLP爱好者"), (8, "强化学习新手"),
    (9, "大模型观察者"), (10, "推荐系统架构师"), (11, "知识图谱构建者"),
    (12, "语音技术达人"), (13, "数据挖掘分析师"), (14, "AIGC创作者"),
    (15, "PyTorch玩家"), (16, "TensorFlow老兵"), (17, "MLOps实践者"),
    (18, "边缘计算探索"), (19, "联邦学习研究者"), (20, "AutoML倡导者"),
]

# ── 10 个分类各 10 条帖子 ──
POST_TEMPLATES: dict[str, list[tuple[str, str, str]]] = {
    "机器学习": [
        ("如何选择合适的机器学习算法？", "在处理分类任务时，面对逻辑回归、SVM、随机森林等众多算法，应该如何根据数据特征和业务需求选择最合适的模型？有没有系统的选型方法论？", "question"),
        ("Scikit-learn Pipeline 最佳实践分享", "总结了一套 Scikit-learn Pipeline 的最佳实践，包括特征预处理、模型训练、超参搜索的完整流程，附代码仓库。", "project"),
        ("交叉验证结果不稳定怎么办？", "使用 5 折交叉验证时，不同 random_state 下结果差异很大，AUC 波动超过 0.05，如何判断模型是否真的有效？", "question"),
        ("特征工程自动化工具对比", "对比了 Featuretools、AutoFeat、TSFresh 三款自动化特征工程工具的功能和性能，附 benchmark 结果。", "project"),
        ("类别不平衡问题的解决思路", "数据集中正负样本比例 1:50，尝试了过采样、欠采样、SMOTE 和 focal loss，想讨论各方法的适用场景。", "question"),
        ("XGBoost 调参经验总结", "分享一份 XGBoost 超参数调优指南，从 learning_rate 到 max_depth 的系统调参策略。", "project"),
        ("如何解读 SHAP 值？", "用 SHAP 解释模型预测时，全局特征重要性和局部解释不一致怎么理解？有没有直观的解释方法？", "question"),
        ("轻量级 AutoML 框架发布", "基于 Optuna + Scikit-learn 的轻量级 AutoML 框架，支持分类和回归自动调参。", "project"),
        ("时间序列特征提取的最佳实践", "处理时间序列数据时，滞后特征、滚动统计特征和频域特征如何组合？有没有通用的特征提取范式？", "question"),
        ("模型可解释性工具汇总", "整理了 LIME、SHAP、Anchors、Counterfactual 等可解释性工具的对比和使用场景。", "project"),
    ],
    "深度学习": [
        ("GPU 显存不足的解决方案汇总", "训练大模型时频繁遇到 CUDA OOM，总结了梯度累积、混合精度训练、模型并行等方案。", "question"),
        ("PyTorch Lightning 项目模板", "分享一个标准化的 PyTorch Lightning 项目模板，包含数据模块、训练流程、日志和部署。", "project"),
        ("Transformer 和 RNN 的选择", "对于中等长度的序列建模任务，Transformer 和 LSTM/GRU 各有什么优劣？何时该用哪个？", "question"),
        ("自监督学习最新进展追踪", "持续更新自监督学习领域的重要论文和代码实现，涵盖 SimCLR、BYOL、MAE 等方法。", "project"),
        ("Batch Size 对训练的影响", "大 batch size 和小 batch size 对泛化能力的影响到底是什么机制？线性缩放规则什么时候适用？", "question"),
        ("神经网络正则化方法对比", "对比了 Dropout、DropConnect、Stochastic Depth、Label Smoothing 的效果和适用场景。", "project"),
        ("学习率调度器选择指南", "CosineAnnealing、OneCycleLR、ReduceLROnPlateau 到底用哪个？不同任务的最佳实践是什么？", "question"),
        ("深度学习训练可视化工具包", "基于 WandB 的训练可视化工具包，支持自定义指标、超参对比和模型版本管理。", "project"),
        ("梯度爆炸/消失的调试方法", "训练深层网络时 loss 变成 NaN 或不下降，如何系统地定位是梯度爆炸还是梯度消失问题？", "question"),
        ("混合精度训练踩坑记录", "使用 AMP 混合精度训练时遇到的常见问题和解决方案，包括 loss scale 调整和精度损失评估。", "project"),
    ],
    "自然语言处理": [
        ("中文预训练模型选型指南", "对比了 BERT-wwm、RoBERTa-zh、ERNIE、MacBERT 在多个中文 NLU 任务上的表现。", "question"),
        ("轻量级 NLP 工具包发布", "基于 HuggingFace Transformers 封装的中文 NLP 工具包，支持分词、NER、情感分析等任务。", "project"),
        ("大模型 Prompt Engineering 技巧", "如何设计有效的 Prompt 来引导大语言模型？Zero-shot、Few-shot 和 CoT 各自的适用场景。", "question"),
        ("中文文本分类实战项目", "从数据清洗到模型部署的完整中文文本分类项目，支持多标签和多分类任务。", "project"),
        ("如何评估生成式模型的质量？", "BLEU、ROUGE 等自动指标和人工评估的差距有多大？有没有更好的评估方法？", "question"),
        ("知识蒸馏在 NLP 中的应用", "将大模型知识蒸馏到小模型的实践指南，包括 TinyBERT、DistilBERT 等方法。", "project"),
        ("对话系统架构设计讨论", "构建一个多轮对话系统时，意图识别、槽位填充和对话管理模块如何设计？", "question"),
        ("中文命名实体识别工具", "基于 BERT-CRF 的中文 NER 工具，支持人名、地名、机构名等实体类型。", "project"),
        ("长文本处理方案对比", "处理超过 512 token 的长文本时，滑动窗口、Longformer、BigBird 各有什么优缺点？", "question"),
        ("RAG 检索增强生成框架", "结合向量检索和 LLM 的 RAG 框架，支持知识库问答和文档对话。", "project"),
    ],
    "计算机视觉": [
        ("目标检测模型选型：YOLO vs DETR", "实时检测场景下 YOLOv8 和 DETR 各有什么优劣？精度和速度如何权衡？", "question"),
        ("图像标注管理平台开源", "一个支持 YOLO/COCO/VOC 格式的图像标注管理平台，含标注、审核、导出全流程。", "project"),
        ("数据增强对检测模型的影响", "Mosaic、MixUp、CopyPaste 等增强策略对 YOLO 系列模型的精度提升有多大？", "question"),
        ("语义分割项目模板", "基于 SegFormer 的语义分割项目模板，支持自定义数据集训练和推理。", "project"),
        ("小目标检测有什么好方法？", "检测图像中的小目标（<32px）时，常规方法效果很差，有没有专门针对小目标的检测策略？", "question"),
        ("实时人体姿态估计方案", "对比了 MediaPipe、YOLOv8-Pose、ViTPose 在实时人体姿态估计中的速度和精度。", "project"),
        ("Vision Transformer vs CNN", "在数据量有限的场景下，ViT 和 ResNet 哪个更适合？迁移学习如何操作？", "question"),
        ("OCR 文字识别工具包", "基于 PaddleOCR 的轻量级文字识别工具包，支持中英文混合识别。", "project"),
        ("图像超分辨率模型对比", "EDSR、RCAN、SwinIR、Real-ESRGAN 在不同场景下的超分效果对比。", "question"),
        ("3D 点云处理工具库", "基于 Open3D 的 3D 点云处理工具库，支持点云分割、配准和可视化。", "project"),
    ],
    "强化学习": [
        ("强化学习入门路径推荐", "零基础学强化学习，应该从 SARSA/Q-Learning 开始还是直接上 DQN？推荐什么教材和课程？", "question"),
        ("Gym 环境封装工具库", "一套标准化的自定义 Gym 环境封装工具，支持多智能体和连续动作空间。", "project"),
        ("PPO 训练不稳定的原因分析", "用 PPO 训练连续控制任务时，reward 曲线剧烈震荡，可能的原因和解决方案？", "question"),
        ("多智能体强化学习框架", "基于 PyMARL 的多智能体强化学习框架，支持 QMIX、MAPPO 等算法。", "project"),
        ("Reward Shaping 的经验和陷阱", "做 Reward Shaping 时容易陷入哪些坑？如何判断 reward 设计是否合理？", "question"),
        ("离线强化学习基准测试", "IQL、CQL、Decision Transformer 在 D4RL 基准上的复现和对比。", "project"),
        ("Sim-to-Real 迁移的实践经验", "从仿真环境迁移到真实机器人时，域随机化和系统辨识哪个效果更好？", "question"),
        ("强化学习可视化工具", "训练过程中的 reward、value、policy 可视化工具，支持视频回放和策略对比。", "project"),
        ("DQN 和 SAC 在离散动作空间的对比", "在 Atari 游戏和离散控制任务中，DQN 和 SAC 的表现差异有多大？", "question"),
        ("强化学习环境 benchmark", "收集了 20+ 经典强化学习环境的最优指标和训练曲线，方便对比。", "project"),
    ],
    "数据挖掘": [
        ("异常检测算法对比", "对比了 Isolation Forest、LOF、One-Class SVM 在不同数据分布下的异常检测效果。", "question"),
        ("关联规则挖掘工具包", "基于 Apriori 和 FP-Growth 的关联规则挖掘工具，支持并行计算。", "project"),
        ("如何处理高维稀疏数据？", "做推荐系统特征时，ID 类特征经过 one-hot 后维度极高，有什么降维或编码策略？", "question"),
        ("时序异常检测框架", "基于 AutoEncoder 和 Prophet 的时序异常检测框架，支持实时检测。", "project"),
        ("聚类算法选择指南", "K-Means、DBSCAN、层次聚类、GMM 在不同数据形状下的表现差异。", "question"),
        ("数据质量评估工具", "自动评估数据完整性、一致性和分布特征的工具，生成数据质量报告。", "project"),
        ("特征选择方法系统对比", "Filter、Wrapper、Embedded 三类特征选择方法在不同规模数据上的效率对比。", "question"),
        ("ETL 流程自动化框架", "声明式的数据 ETL 框架，支持数据源配置、转换规则和调度管理。", "project"),
        ("如何发现数据中的潜在模式？", "面对一个全新的数据集，应该按照什么流程去探索和发现有价值的模式？", "question"),
        ("大规模图挖掘工具", "基于 NetworkX 和 GraphTool 的大规模图挖掘工具，支持社区发现和影响力分析。", "project"),
    ],
    "知识图谱": [
        ("知识图谱构建流程详解", "从非结构化文本到知识图谱，完整的构建流程包括哪些步骤？有哪些成熟工具？", "question"),
        ("Neo4j 图数据库管理工具", "一个可视化的 Neo4j 图数据库管理工具，支持 Cypher 编辑和图谱浏览。", "project"),
        ("实体链接方法对比", "基于 BERT 的实体链接和传统 EL 方法的精度差异有多大？中文场景下有什么挑战？", "question"),
        ("知识图谱问答系统", "基于知识图谱的问答系统，支持自然语言到 SPARQL 的转换和多跳推理。", "project"),
        ("关系抽取最新进展", "远程监督关系抽取中如何处理噪声标签？有没有好的去噪方法？", "question"),
        ("图谱可视化组件库", "基于 D3.js 的知识图谱可视化组件库，支持大规模图谱的交互式浏览。", "project"),
        ("知识推理方法综述", "基于嵌入的推理（TransE、RotatE）和基于规则的推理（Rule-based）各自的优劣？", "question"),
        ("本体构建辅助工具", "辅助领域本体构建的工具，支持术语提取、层次结构发现和一致性检查。", "project"),
        ("多源知识图谱融合策略", "不同来源的知识图谱如何进行实体对齐和知识融合？有什么实践经验？", "question"),
        ("知识图谱嵌入 benchmark", "FB15k-237、WN18RR 等基准数据集上的知识图谱嵌入模型复现和对比。", "project"),
    ],
    "语音识别": [
        ("Whisper 模型微调经验", "用 Whisper 做中文语音识别时，是否需要微调？微调数据量需要多少？", "question"),
        ("语音数据预处理工具包", "支持音频格式转换、VAD 切分、数据增强的语音数据预处理工具包。", "project"),
        ("端到端语音识别 vs 传统方案", "Conformer-Transducer 和传统 GMM-HMM 方案在中文识别中各自的优劣？", "question"),
        ("实时语音转写服务", "基于 WebSocket 的实时语音转写服务，支持流式识别和标点预测。", "project"),
        ("语音增强方法对比", "在噪声环境下，传统谱减法和深度学习语音增强（如 Demucs）的效果差异？", "question"),
        ("TTS 语音合成工具", "基于 VITS 的多说话人语音合成工具，支持中英文混合合成。", "project"),
        ("说话人识别系统搭建", "如何搭建一个基于 ECAPA-TDNN 的说话人识别/声纹验证系统？", "question"),
        ("音频标注工具", "支持时间戳标注和说话人标注的音频标注工具，输出格式兼容 Kaldi 和 ESPnet。", "project"),
        ("远场语音识别的挑战", "远场（3m+）语音识别的难点和解决方案，麦克风阵列和波束成形的效果？", "question"),
        ("语音情感识别数据集", "整理了 IEMOCAP、RAVDESS 等语音情感识别数据集的对比和使用指南。", "project"),
    ],
    "推荐系统": [
        ("推荐系统冷启动策略", "新用户/新物品的冷启动问题有哪些实用策略？内容推荐和热度推荐各有什么局限？", "question"),
        ("推荐系统框架开源", "基于 PyTorch 的推荐系统框架，支持 FM、DeepFM、DIN、DIEN 等模型。", "project"),
        ("特征交叉方法演进", "从 FM 到 DeepFM 到 DCN-v2，特征交叉方法的演进脉络和效果对比。", "question"),
        ("实时推荐引擎", "基于 Flink + Redis 的实时推荐引擎，支持特征实时更新和模型在线推理。", "project"),
        ("A/B 测试在推荐系统中的应用", "推荐系统的 A/B 测试需要注意什么？如何设计合理的分流和评估指标？", "question"),
        ("召回层算法对比", "协同过滤、向量召回、图召回在百万级物品库上的召回率和延迟对比。", "project"),
        ("多目标优化在推荐中的实践", "同时优化点击率、转化率和停留时长时，如何设计损失函数和权重？", "question"),
        ("推荐可解释性工具", "为推荐结果生成自然语言解释的工具，基于注意力权重和特征重要性。", "project"),
        ("序列推荐模型对比", "GRU4Rec、SASRec、BERT4Rec 在电商推荐场景中的效果对比。", "question"),
        ("推荐系统评估工具包", "支持离线评估（NDCG、Hit Rate）和在线评估的推荐系统评估框架。", "project"),
    ],
    "大模型与AIGC": [
        ("LoRA 微调实践指南", "用 LoRA 微调 LLaMA 系列模型时，rank 设多少合适？不同 rank 对效果的影响？", "question"),
        ("大模型推理加速框架", "基于 vLLM 的推理加速框架，支持连续批处理和 PagedAttention。", "project"),
        ("Prompt 注入攻击与防御", "大模型的 Prompt 注入攻击有哪些形式？如何设计系统级的防御策略？", "question"),
        ("AIGC 内容生成平台", "支持文生图、图生图、文生视频的多模态 AIGC 平台，集成了 Stable Diffusion 和 Sora。", "project"),
        ("大模型幻觉问题如何解决？", "大语言模型的幻觉（Hallucination）有哪些缓解方法？RAG 和 Self-Consistency 效果如何？", "question"),
        ("中文大模型 benchmark", "在 C-Eval、CMMLU 等中文基准上测试了多个开源大模型的结果。", "project"),
        ("向量数据库选型对比", "Milvus、Pinecone、Weaviate、Chroma 在百万级向量检索中的性能对比。", "question"),
        ("LangChain 应用开发模板", "基于 LangChain 的 LLM 应用开发模板，包含 RAG、Agent 和 Chain 等常见模式。", "project"),
        ("如何评估大模型的生成质量？", "自动评估（GPT-4-as-judge）和人工评估各自的可靠性和成本？", "question"),
        ("AI 绘画工作流工具", "ComfyUI 工作流模板集合，包含人像修复、风格迁移和批量生成等工作流。", "project"),
    ],
}

REPLY_TEMPLATES = [
    "感谢分享，非常实用的内容！已收藏备用。",
    "我之前也遇到过类似问题，后来发现是数据预处理的问题，你可以检查一下。",
    "写得很好，能否补充一下在更大规模数据上的测试结果？",
    "这个方案我试过，效果不错，但在边缘情况下有些问题，建议加一些 fallback 逻辑。",
    "请问这个方案在 GPU 和 CPU 上的性能差异大吗？",
    "推荐参考 XX 论文，里面提到了类似的方法，可以对比一下。",
    "代码仓库链接好像失效了，能更新一下吗？",
    "非常详细！不过我觉得第 3 步可以优化一下，用更高效的数据结构。",
    "我们团队在生产环境中用了类似方案，跑了半年了，稳定性还行。",
    "补充一点：如果数据量特别大，建议用分布式训练，单卡会很慢。",
    "这个思路很新颖，但实现复杂度会不会太高？有没有更轻量的替代方案？",
    "实测了一下，在我的数据集上效果提升明显，AUC 提高了约 3%。",
    "请问有没有和 XXX 方法的对比实验？想看看两者的差异。",
    "文档写得很清晰，新手也能跟着操作，点赞！",
    "我在 Windows 环境下遇到了兼容性问题，Linux 下正常，有人遇到类似情况吗？",
]

def seed():
    init_community_db()
    now = time.time()
    post_ids = []

    with _conn() as con:
        for cat, posts in POST_TEMPLATES.items():
            for title, content, post_type in posts:
                uid, uname = random.choice(USERS)
                ts = now - random.randint(3600, 3600 * 24 * 30)  # 过去 30 天内
                cur = con.execute(
                    """
                    INSERT INTO posts (user_id, username, title, content, category, post_type,
                                       attachment_name, attachment_path, project_link, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
                    """,
                    (uid, uname, title, content, cat, post_type, ts, ts),
                )
                post_ids.append(cur.lastrowid)

        # 每条帖子 5 条评论
        for pid in post_ids:
            for _ in range(5):
                uid, uname = random.choice(USERS)
                content = random.choice(REPLY_TEMPLATES)
                ts = now - random.randint(0, 3600 * 24 * 7)  # 过去 7 天内
                con.execute(
                    "INSERT INTO replies (post_id, user_id, username, content, created_at) VALUES (?, ?, ?, ?, ?)",
                    (pid, uid, uname, content, ts),
                )

    print(f"已插入 {len(post_ids)} 条帖子和 {len(post_ids) * 5} 条评论。")


if __name__ == "__main__":
    seed()
