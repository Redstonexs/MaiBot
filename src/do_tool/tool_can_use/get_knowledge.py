from src.do_tool.tool_can_use.base_tool import BaseTool
from src.plugins.chat.utils import get_embedding
from src.common.database import db
from src.common.logger_manager import get_logger
from typing import Any, Union

logger = get_logger("get_knowledge_tool")


class SearchKnowledgeTool(BaseTool):
    """从知识库中搜索相关信息的工具"""

    name = "search_knowledge"
    description = "使用工具从知识库中搜索相关信息"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询关键词"},
            "threshold": {"type": "number", "description": "相似度阈值，0.0到1.0之间"},
        },
        "required": ["query"],
    }

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行知识库搜索

        Args:
            function_args: 工具参数

        Returns:
            dict: 工具执行结果
        """
        try:
            query = function_args.get("query")
            threshold = function_args.get("threshold", 0.4)

            # 调用知识库搜索
            embedding = await get_embedding(query, request_type="info_retrieval")
            if embedding:
                knowledge_info = self.get_info_from_db(embedding, limit=3, threshold=threshold)
                if knowledge_info:
                    content = f"你知道这些知识: {knowledge_info}"
                else:
                    content = f"你不太了解有关{query}的知识"
                return {"type": "knowledge", "id": query, "content": content}
            return {"type": "info", "id": query, "content": f"无法获取关于'{query}'的嵌入向量，你知识库炸了"}
        except Exception as e:
            logger.error(f"知识库搜索工具执行失败: {str(e)}")
            return {"type": "info", "id": query, "content": f"知识库搜索失败，炸了: {str(e)}"}

    @staticmethod
    def get_info_from_db(
        query_embedding: list, limit: int = 1, threshold: float = 0.5, return_raw: bool = False
    ) -> Union[str, list]:
        """从数据库中获取相关信息

        Args:
            query_embedding: 查询的嵌入向量
            limit: 最大返回结果数
            threshold: 相似度阈值
            return_raw: 是否返回原始结果

        Returns:
            Union[str, list]: 格式化的信息字符串或原始结果列表
        """
        if not query_embedding:
            return "" if not return_raw else []

        # 使用余弦相似度计算
        pipeline = [
            {
                "$addFields": {
                    "dotProduct": {
                        "$reduce": {
                            "input": {"$range": [0, {"$size": "$embedding"}]},
                            "initialValue": 0,
                            "in": {
                                "$add": [
                                    "$$value",
                                    {
                                        "$multiply": [
                                            {"$arrayElemAt": ["$embedding", "$$this"]},
                                            {"$arrayElemAt": [query_embedding, "$$this"]},
                                        ]
                                    },
                                ]
                            },
                        }
                    },
                    "magnitude1": {
                        "$sqrt": {
                            "$reduce": {
                                "input": "$embedding",
                                "initialValue": 0,
                                "in": {"$add": ["$$value", {"$multiply": ["$$this", "$$this"]}]},
                            }
                        }
                    },
                    "magnitude2": {
                        "$sqrt": {
                            "$reduce": {
                                "input": query_embedding,
                                "initialValue": 0,
                                "in": {"$add": ["$$value", {"$multiply": ["$$this", "$$this"]}]},
                            }
                        }
                    },
                }
            },
            {"$addFields": {"similarity": {"$divide": ["$dotProduct", {"$multiply": ["$magnitude1", "$magnitude2"]}]}}},
            {
                "$match": {
                    "similarity": {"$gte": threshold}  # 只保留相似度大于等于阈值的结果
                }
            },
            {"$sort": {"similarity": -1}},
            {"$limit": limit},
            {"$project": {"content": 1, "similarity": 1}},
        ]

        results = list(db.knowledges.aggregate(pipeline))
        logger.debug(f"知识库查询结果数量: {len(results)}")

        if not results:
            return "" if not return_raw else []

        if return_raw:
            return results
        else:
            # 返回所有找到的内容，用换行分隔
            return "\n".join(str(result["content"]) for result in results)


# 注册工具
# register_tool(SearchKnowledgeTool)
