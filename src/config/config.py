import os
import tomlkit
import shutil

from datetime import datetime
from tomlkit import TOMLDocument
from tomlkit.items import Table, KeyType
from dataclasses import field, dataclass
from rich.traceback import install

from src.common.logger import get_logger
from src.config.config_base import ConfigBase
from src.config.official_configs import (
    BotConfig,
    PersonalityConfig,
    ExpressionConfig,
    ChatConfig,
    NormalChatConfig,
    EmojiConfig,
    MemoryConfig,
    MoodConfig,
    KeywordReactionConfig,
    ChineseTypoConfig,
    ResponsePostProcessConfig,
    ResponseSplitterConfig,
    TelemetryConfig,
    ExperimentalConfig,
    ModelConfig,
    MessageReceiveConfig,
    MaimMessageConfig,
    LPMMKnowledgeConfig,
    RelationshipConfig,
    ToolConfig,
    VoiceConfig,
    DebugConfig,
    CustomPromptConfig,
)

install(extra_lines=3)


# 配置主程序日志格式
logger = get_logger("config")

# 获取当前文件所在目录的父目录的父目录（即MaiBot项目根目录）
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "template")

# 考虑到，实际上配置文件中的mai_version是不会自动更新的,所以采用硬编码
# 对该字段的更新，请严格参照语义化版本规范：https://semver.org/lang/zh-CN/
MMC_VERSION = "0.9.1"


def get_key_comment(toml_table, key):
    # 获取key的注释（如果有）
    if hasattr(toml_table, "trivia") and hasattr(toml_table.trivia, "comment"):
        return toml_table.trivia.comment
    if hasattr(toml_table, "value") and isinstance(toml_table.value, dict):
        item = toml_table.value.get(key)
        if item is not None and hasattr(item, "trivia"):
            return item.trivia.comment
    if hasattr(toml_table, "keys"):
        for k in toml_table.keys():
            if isinstance(k, KeyType) and k.key == key:
                return k.trivia.comment
    return None


def compare_dicts(new, old, path=None, logs=None):
    # 递归比较两个dict，找出新增和删减项，收集注释
    if path is None:
        path = []
    if logs is None:
        logs = []
    # 新增项
    for key in new:
        if key == "version":
            continue
        if key not in old:
            comment = get_key_comment(new, key)
            logs.append(f"新增: {'.'.join(path + [str(key)])}  注释: {comment if comment else '无'}")
        elif isinstance(new[key], (dict, Table)) and isinstance(old.get(key), (dict, Table)):
            compare_dicts(new[key], old[key], path + [str(key)], logs)
    # 删减项
    for key in old:
        if key == "version":
            continue
        if key not in new:
            comment = get_key_comment(old, key)
            logs.append(f"删减: {'.'.join(path + [str(key)])}  注释: {comment if comment else '无'}")
    return logs


def get_value_by_path(d, path):
    for k in path:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return None
    return d


def set_value_by_path(d, path, value):
    for k in path[:-1]:
        if k not in d or not isinstance(d[k], dict):
            d[k] = {}
        d = d[k]
    d[path[-1]] = value


def compare_default_values(new, old, path=None, logs=None, changes=None):
    # 递归比较两个dict，找出默认值变化项
    if path is None:
        path = []
    if logs is None:
        logs = []
    if changes is None:
        changes = []
    for key in new:
        if key == "version":
            continue
        if key in old:
            if isinstance(new[key], (dict, Table)) and isinstance(old[key], (dict, Table)):
                compare_default_values(new[key], old[key], path + [str(key)], logs, changes)
            else:
                # 只要值发生变化就记录
                if new[key] != old[key]:
                    logs.append(
                        f"默认值变化: {'.'.join(path + [str(key)])}  旧默认值: {old[key]}  新默认值: {new[key]}"
                    )
                    changes.append((path + [str(key)], old[key], new[key]))
    return logs, changes


def update_config():
    # 获取根目录路径
    old_config_dir = os.path.join(CONFIG_DIR, "old")
    compare_dir = os.path.join(TEMPLATE_DIR, "compare")

    # 定义文件路径
    template_path = os.path.join(TEMPLATE_DIR, "bot_config_template.toml")
    old_config_path = os.path.join(CONFIG_DIR, "bot_config.toml")
    new_config_path = os.path.join(CONFIG_DIR, "bot_config.toml")
    compare_path = os.path.join(compare_dir, "bot_config_template.toml")

    # 创建compare目录（如果不存在）
    os.makedirs(compare_dir, exist_ok=True)

    # 处理compare下的模板文件
    def get_version_from_toml(toml_path):
        if not os.path.exists(toml_path):
            return None
        with open(toml_path, "r", encoding="utf-8") as f:
            doc = tomlkit.load(f)
        if "inner" in doc and "version" in doc["inner"]:  # type: ignore
            return doc["inner"]["version"]  # type: ignore
        return None

    template_version = get_version_from_toml(template_path)
    compare_version = get_version_from_toml(compare_path)

    def version_tuple(v):
        if v is None:
            return (0,)
        return tuple(int(x) if x.isdigit() else 0 for x in str(v).replace("v", "").split("-")[0].split("."))

    # 先读取 compare 下的模板（如果有），用于默认值变动检测
    if os.path.exists(compare_path):
        with open(compare_path, "r", encoding="utf-8") as f:
            compare_config = tomlkit.load(f)
    else:
        compare_config = None

    # 读取当前模板
    with open(template_path, "r", encoding="utf-8") as f:
        new_config = tomlkit.load(f)

    # 检查默认值变化并处理（只有 compare_config 存在时才做）
    if compare_config is not None:
        # 读取旧配置
        with open(old_config_path, "r", encoding="utf-8") as f:
            old_config = tomlkit.load(f)
        logs, changes = compare_default_values(new_config, compare_config)
        if logs:
            logger.info("检测到模板默认值变动如下：")
            for log in logs:
                logger.info(log)
            # 检查旧配置是否等于旧默认值，如果是则更新为新默认值
            for path, old_default, new_default in changes:
                old_value = get_value_by_path(old_config, path)
                if old_value == old_default:
                    set_value_by_path(old_config, path, new_default)
                    logger.info(
                        f"已自动将配置 {'.'.join(path)} 的值从旧默认值 {old_default} 更新为新默认值 {new_default}"
                    )
        else:
            logger.info("未检测到模板默认值变动")
        # 保存旧配置的变更（后续合并逻辑会用到 old_config）
    else:
        old_config = None

    # 检查 compare 下没有模板，或新模板版本更高，则复制
    if not os.path.exists(compare_path):
        shutil.copy2(template_path, compare_path)
        logger.info(f"已将模板文件复制到: {compare_path}")
    else:
        if version_tuple(template_version) > version_tuple(compare_version):
            shutil.copy2(template_path, compare_path)
            logger.info(f"模板版本较新，已替换compare下的模板: {compare_path}")
        else:
            logger.debug(f"compare下的模板版本不低于当前模板，无需替换: {compare_path}")

    # 检查配置文件是否存在
    if not os.path.exists(old_config_path):
        logger.info("配置文件不存在，从模板创建新配置")
        os.makedirs(CONFIG_DIR, exist_ok=True)  # 创建文件夹
        shutil.copy2(template_path, old_config_path)  # 复制模板文件
        logger.info(f"已创建新配置文件，请填写后重新运行: {old_config_path}")
        # 如果是新创建的配置文件,直接返回
        quit()

    # 读取旧配置文件和模板文件（如果前面没读过 old_config，这里再读一次）
    if old_config is None:
        with open(old_config_path, "r", encoding="utf-8") as f:
            old_config = tomlkit.load(f)
    # new_config 已经读取

    # 读取 compare_config 只用于默认值变动检测，后续合并逻辑不再用

    # 检查version是否相同
    if old_config and "inner" in old_config and "inner" in new_config:
        old_version = old_config["inner"].get("version")  # type: ignore
        new_version = new_config["inner"].get("version")  # type: ignore
        if old_version and new_version and old_version == new_version:
            logger.info(f"检测到配置文件版本号相同 (v{old_version})，跳过更新")
            return
        else:
            logger.info(
                f"\n----------------------------------------\n检测到版本号不同: 旧版本 v{old_version} -> 新版本 v{new_version}\n----------------------------------------"
            )
    else:
        logger.info("已有配置文件未检测到版本号，可能是旧版本。将进行更新")

    # 创建old目录（如果不存在）
    os.makedirs(old_config_dir, exist_ok=True)  # 生成带时间戳的新文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    old_backup_path = os.path.join(old_config_dir, f"bot_config_{timestamp}.toml")

    # 移动旧配置文件到old目录
    shutil.move(old_config_path, old_backup_path)
    logger.info(f"已备份旧配置文件到: {old_backup_path}")

    # 复制模板文件到配置目录
    shutil.copy2(template_path, new_config_path)
    logger.info(f"已创建新配置文件: {new_config_path}")

    # 输出新增和删减项及注释
    if old_config:
        logger.info("配置项变动如下：\n----------------------------------------")
        logs = compare_dicts(new_config, old_config)
        if logs:
            for log in logs:
                logger.info(log)
        else:
            logger.info("无新增或删减项")

    def update_dict(target: TOMLDocument | dict | Table, source: TOMLDocument | dict):
        """
        将source字典的值更新到target字典中（如果target中存在相同的键）
        """
        for key, value in source.items():
            # 跳过version字段的更新
            if key == "version":
                continue
            if key in target:
                target_value = target[key]
                if isinstance(value, dict) and isinstance(target_value, (dict, Table)):
                    update_dict(target_value, value)
                else:
                    try:
                        # 对数组类型进行特殊处理
                        if isinstance(value, list):
                            # 如果是空数组，确保它保持为空数组
                            target[key] = tomlkit.array(str(value)) if value else tomlkit.array()
                        else:
                            # 其他类型使用item方法创建新值
                            target[key] = tomlkit.item(value)
                    except (TypeError, ValueError):
                        # 如果转换失败，直接赋值
                        target[key] = value

    # 将旧配置的值更新到新配置中
    logger.info("开始合并新旧配置...")
    update_dict(new_config, old_config)

    # 保存更新后的配置（保留注释和格式）
    with open(new_config_path, "w", encoding="utf-8") as f:
        f.write(tomlkit.dumps(new_config))
    logger.info("配置文件更新完成，建议检查新配置文件中的内容，以免丢失重要信息")
    quit()


@dataclass
class Config(ConfigBase):
    """总配置类"""

    MMC_VERSION: str = field(default=MMC_VERSION, repr=False, init=False)  # 硬编码的版本信息

    bot: BotConfig
    personality: PersonalityConfig
    relationship: RelationshipConfig
    chat: ChatConfig
    message_receive: MessageReceiveConfig
    normal_chat: NormalChatConfig
    emoji: EmojiConfig
    expression: ExpressionConfig
    memory: MemoryConfig
    mood: MoodConfig
    keyword_reaction: KeywordReactionConfig
    chinese_typo: ChineseTypoConfig
    response_post_process: ResponsePostProcessConfig
    response_splitter: ResponseSplitterConfig
    telemetry: TelemetryConfig
    experimental: ExperimentalConfig
    model: ModelConfig
    maim_message: MaimMessageConfig
    lpmm_knowledge: LPMMKnowledgeConfig
    tool: ToolConfig
    debug: DebugConfig
    custom_prompt: CustomPromptConfig
    voice: VoiceConfig

def load_config(config_path: str) -> Config:
    """
    加载配置文件
    :param config_path: 配置文件路径
    :return: Config对象
    """
    # 读取配置文件
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = tomlkit.load(f)

    # 创建Config对象
    try:
        return Config.from_dict(config_data)
    except Exception as e:
        logger.critical("配置文件解析失败")
        raise e


def get_config_dir() -> str:
    """
    获取配置目录
    :return: 配置目录路径
    """
    return CONFIG_DIR


# 获取配置文件路径
logger.info(f"MaiCore当前版本: {MMC_VERSION}")
update_config()

logger.info("正在品鉴配置文件...")
global_config = load_config(config_path=os.path.join(CONFIG_DIR, "bot_config.toml"))
logger.info("非常的新鲜，非常的美味！")
