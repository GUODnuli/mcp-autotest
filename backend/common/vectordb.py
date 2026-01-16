"""
向量知识库模块

提供向量数据库的封装，支持语义检索和知识存储。
用于突破 Dify API 20k token 的上下文限制。

支持的后端：
- ChromaDB（默认）
- Faiss
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from abc import ABC, abstractmethod

from ..common.logger import get_logger


class VectorDBError(Exception):
    """向量数据库操作异常"""
    pass


class VectorDBBackend(ABC):
    """向量数据库后端抽象基类"""
    
    @abstractmethod
    def initialize(self, config: Dict[str, Any]):
        """初始化数据库"""
        pass
    
    @abstractmethod
    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """添加文档"""
        pass
    
    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """语义搜索"""
        pass
    
    @abstractmethod
    def delete(self, ids: List[str]):
        """删除文档"""
        pass
    
    @abstractmethod
    def update(self, ids: List[str], metadatas: List[Dict[str, Any]]):
        """更新元数据"""
        pass
    
    @abstractmethod
    def count(self) -> int:
        """获取文档数量"""
        pass


class ChromaDBBackend(VectorDBBackend):
    """ChromaDB 后端实现"""
    
    def __init__(self):
        self.client = None
        self.collection = None
        self.logger = get_logger()
    
    def initialize(self, config: Dict[str, Any]):
        """初始化 ChromaDB"""
        try:
            import chromadb
            from chromadb.config import Settings
            
            persist_directory = config.get("persist_directory", "./storage/vectordb")
            collection_name = config.get("collection_name", "mcp_api_test_knowledge")
            
            # 确保目录存在
            Path(persist_directory).mkdir(parents=True, exist_ok=True)
            
            # 创建客户端
            self.client = chromadb.PersistentClient(
                path=persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # 获取或创建集合
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"description": "MCP API Test Knowledge Base"}
            )
            
            self.logger.info(
                f"ChromaDB 初始化成功 | 集合: {collection_name} | "
                f"文档数: {self.collection.count()}"
            )
        
        except ImportError:
            raise VectorDBError(
                "ChromaDB 未安装，请执行: pip install chromadb"
            )
        except Exception as e:
            raise VectorDBError(f"ChromaDB 初始化失败: {e}")
    
    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """添加文档到 ChromaDB"""
        try:
            if not ids:
                import uuid
                ids = [str(uuid.uuid4()) for _ in documents]
            
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            
            self.logger.debug(f"添加文档成功 | 数量: {len(documents)}")
            return ids
        
        except Exception as e:
            raise VectorDBError(f"添加文档失败: {e}")
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """语义搜索"""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=filter
            )
            
            # 解析结果
            documents = results['documents'][0]
            distances = results['distances'][0]
            metadatas = results['metadatas'][0]
            
            # 转换为 (document, similarity, metadata) 元组列表
            # ChromaDB 返回的是距离，需要转换为相似度
            search_results = [
                (doc, 1.0 - dist, meta)
                for doc, dist, meta in zip(documents, distances, metadatas)
            ]
            
            self.logger.debug(f"搜索完成 | 查询: {query[:50]}... | 结果数: {len(search_results)}")
            return search_results
        
        except Exception as e:
            raise VectorDBError(f"搜索失败: {e}")
    
    def delete(self, ids: List[str]):
        """删除文档"""
        try:
            self.collection.delete(ids=ids)
            self.logger.debug(f"删除文档成功 | 数量: {len(ids)}")
        
        except Exception as e:
            raise VectorDBError(f"删除文档失败: {e}")
    
    def update(self, ids: List[str], metadatas: List[Dict[str, Any]]):
        """更新元数据"""
        try:
            self.collection.update(
                ids=ids,
                metadatas=metadatas
            )
            self.logger.debug(f"更新元数据成功 | 数量: {len(ids)}")
        
        except Exception as e:
            raise VectorDBError(f"更新元数据失败: {e}")
    
    def count(self) -> int:
        """获取文档数量"""
        try:
            return self.collection.count()
        except Exception as e:
            raise VectorDBError(f"获取文档数量失败: {e}")


class FaissBackend(VectorDBBackend):
    """Faiss 后端实现（用于高性能场景）"""
    
    def __init__(self):
        self.index = None
        self.documents = []
        self.metadatas = []
        self.id_map = {}
        self.logger = get_logger()
        self.embedding_model = None
    
    def initialize(self, config: Dict[str, Any]):
        """初始化 Faiss"""
        try:
            import faiss
            import numpy as np
            from sentence_transformers import SentenceTransformer
            
            # 加载嵌入模型
            embedding_model_name = config.get(
                "embedding_model",
                "sentence-transformers/all-MiniLM-L6-v2"
            )
            self.embedding_model = SentenceTransformer(embedding_model_name)
            
            # 获取向量维度
            dimension = self.embedding_model.get_sentence_embedding_dimension()
            
            # 创建 Faiss 索引（使用 L2 距离）
            self.index = faiss.IndexFlatL2(dimension)
            
            # 加载持久化数据（如果存在）
            persist_directory = config.get("persist_directory", "./storage/vectordb")
            index_path = Path(persist_directory) / "faiss.index"
            
            if index_path.exists():
                self.index = faiss.read_index(str(index_path))
                # TODO: 加载 documents 和 metadatas
            
            self.logger.info(f"Faiss 初始化成功 | 维度: {dimension} | 文档数: {self.index.ntotal}")
        
        except ImportError:
            raise VectorDBError(
                "Faiss 或 sentence-transformers 未安装，请执行: "
                "pip install faiss-cpu sentence-transformers"
            )
        except Exception as e:
            raise VectorDBError(f"Faiss 初始化失败: {e}")
    
    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """添加文档到 Faiss"""
        try:
            import numpy as np
            
            if not ids:
                import uuid
                ids = [str(uuid.uuid4()) for _ in documents]
            
            # 生成嵌入向量
            embeddings = self.embedding_model.encode(documents)
            embeddings = np.array(embeddings).astype('float32')
            
            # 添加到索引
            start_id = len(self.documents)
            self.index.add(embeddings)
            
            # 保存文档和元数据
            self.documents.extend(documents)
            self.metadatas.extend(metadatas)
            
            # 建立 ID 映射
            for i, doc_id in enumerate(ids):
                self.id_map[doc_id] = start_id + i
            
            self.logger.debug(f"添加文档成功 | 数量: {len(documents)}")
            return ids
        
        except Exception as e:
            raise VectorDBError(f"添加文档失败: {e}")
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """语义搜索"""
        try:
            import numpy as np
            
            # 生成查询向量
            query_embedding = self.embedding_model.encode([query])
            query_embedding = np.array(query_embedding).astype('float32')
            
            # 搜索
            distances, indices = self.index.search(query_embedding, top_k)
            
            # 转换结果
            results = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx < len(self.documents):
                    doc = self.documents[idx]
                    meta = self.metadatas[idx]
                    
                    # 应用过滤器
                    if filter:
                        if not all(meta.get(k) == v for k, v in filter.items()):
                            continue
                    
                    # 转换距离为相似度（L2 距离越小越相似）
                    similarity = 1.0 / (1.0 + dist)
                    results.append((doc, similarity, meta))
            
            self.logger.debug(f"搜索完成 | 查询: {query[:50]}... | 结果数: {len(results)}")
            return results
        
        except Exception as e:
            raise VectorDBError(f"搜索失败: {e}")
    
    def delete(self, ids: List[str]):
        """删除文档（Faiss 不支持单独删除，需要重建索引）"""
        raise VectorDBError("Faiss 后端不支持删除操作")
    
    def update(self, ids: List[str], metadatas: List[Dict[str, Any]]):
        """更新元数据"""
        try:
            for doc_id, metadata in zip(ids, metadatas):
                if doc_id in self.id_map:
                    idx = self.id_map[doc_id]
                    self.metadatas[idx] = metadata
            
            self.logger.debug(f"更新元数据成功 | 数量: {len(ids)}")
        
        except Exception as e:
            raise VectorDBError(f"更新元数据失败: {e}")
    
    def count(self) -> int:
        """获取文档数量"""
        return self.index.ntotal


class VectorDB:
    """向量数据库管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化向量数据库
        
        Args:
            config: 配置字典（来自 vectordb.toml）
        """
        self.config = config
        self.logger = get_logger()
        
        # 选择后端
        backend_type = config.get("backend", "chromadb").lower()
        
        if backend_type == "chromadb":
            self.backend = ChromaDBBackend()
        elif backend_type == "faiss":
            self.backend = FaissBackend()
        else:
            raise VectorDBError(f"不支持的后端类型: {backend_type}")
        
        # 初始化后端
        self.backend.initialize(config)
        
        # 检索配置
        self.retrieval_config = config.get("retrieval", {})
        self.top_k = self.retrieval_config.get("top_k", 10)
        self.similarity_threshold = self.retrieval_config.get("similarity_threshold", 0.7)
        
        self.logger.info(f"向量数据库初始化完成 | 后端: {backend_type}")
    
    def add_interface_knowledge(
        self,
        interface_name: str,
        interface_data: Dict[str, Any],
        task_id: str
    ) -> str:
        """
        添加接口知识
        
        Args:
            interface_name: 接口名称
            interface_data: 接口数据
            task_id: 关联任务 ID
            
        Returns:
            文档 ID
        """
        # 构建文档内容
        document = self._build_interface_document(interface_name, interface_data)
        
        # 构建元数据（ChromaDB 只支持 str/int/float/bool 类型）
        metadata = {
            "type": "interface",
            "interface_name": interface_name,
            "method": interface_data.get("method", ""),
            "path": interface_data.get("path", ""),
            "task_id": task_id,
            "created_at": self._get_timestamp()
        }
        
        # 列表类型需要转换为字符串
        if "tags" in interface_data and interface_data["tags"]:
            metadata["tags"] = ",".join(str(t) for t in interface_data["tags"])
        
        # 添加到向量库
        ids = self.backend.add_documents([document], [metadata])
        
        self.logger.info(f"接口知识已添加 | interface: {interface_name} | id: {ids[0]}")
        return ids[0]
    
    def add_testcase_knowledge(
        self,
        testcase_id: str,
        testcase_data: Dict[str, Any],
        task_id: str
    ) -> str:
        """
        添加测试用例知识
        
        Args:
            testcase_id: 用例 ID
            testcase_data: 用例数据
            task_id: 关联任务 ID
            
        Returns:
            文档 ID
        """
        # 构建文档内容
        document = self._build_testcase_document(testcase_id, testcase_data)
        
        # 构建元数据（ChromaDB 只支持 str/int/float/bool 类型）
        metadata = {
            "type": "testcase",
            "testcase_id": testcase_id,
            "interface_name": testcase_data.get("interface_name", ""),
            "task_id": task_id,
            "created_at": self._get_timestamp()
        }
        
        # 列表类型需要转换为字符串
        if "tags" in testcase_data and testcase_data["tags"]:
            metadata["tags"] = ",".join(str(t) for t in testcase_data["tags"])
        
        # 添加到向量库
        ids = self.backend.add_documents([document], [metadata])
        
        self.logger.debug(f"测试用例知识已添加 | testcase: {testcase_id}")
        return ids[0]
    
    def search_similar_interfaces(
        self,
        query: str,
        top_k: Optional[int] = None,
        task_id: Optional[str] = None
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        搜索相似接口
        
        Args:
            query: 查询文本
            top_k: 返回数量
            task_id: 按任务过滤（可选）
            
        Returns:
            [(document, similarity, metadata), ...]
        """
        filter = {"type": "interface"}
        if task_id:
            filter["task_id"] = task_id
        
        results = self.backend.search(
            query,
            top_k=top_k or self.top_k,
            filter=filter
        )
        
        # 过滤低相似度结果
        filtered_results = [
            (doc, sim, meta)
            for doc, sim, meta in results
            if sim >= self.similarity_threshold
        ]
        
        return filtered_results
    
    def search_similar_testcases(
        self,
        query: str,
        top_k: Optional[int] = None
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """搜索相似测试用例"""
        filter = {"type": "testcase"}
        
        results = self.backend.search(
            query,
            top_k=top_k or self.top_k,
            filter=filter
        )
        
        filtered_results = [
            (doc, sim, meta)
            for doc, sim, meta in results
            if sim >= self.similarity_threshold
        ]
        
        return filtered_results
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_documents": self.backend.count(),
            "backend": self.config.get("backend"),
            "collection_name": self.config.get("collection_name"),
        }
    
    def _build_interface_document(
        self,
        interface_name: str,
        interface_data: Dict[str, Any]
    ) -> str:
        """构建接口文档文本"""
        parts = [
            f"接口名称: {interface_name}",
            f"路径: {interface_data.get('path', '')}",
            f"方法: {interface_data.get('method', '')}",
            f"描述: {interface_data.get('description', '')}",
        ]
        
        # 添加参数信息
        if "parameters" in interface_data and interface_data["parameters"]:
            params = interface_data["parameters"]
            if isinstance(params, list):
                param_str = ", ".join([p.get("name", "") for p in params if isinstance(p, dict)])
                if param_str:
                    parts.append(f"参数: {param_str}")
        
        # 添加请求体信息
        if "request_body" in interface_data and interface_data["request_body"]:
            req_body = interface_data["request_body"]
            if isinstance(req_body, dict) and "properties" in req_body:
                props = req_body["properties"]
                if isinstance(props, dict):
                    prop_names = ", ".join(props.keys())
                    if prop_names:
                        parts.append(f"请求字段: {prop_names}")
        
        return " | ".join(parts)
    
    def _build_testcase_document(
        self,
        testcase_id: str,
        testcase_data: Dict[str, Any]
    ) -> str:
        """构建测试用例文档文本"""
        parts = [
            f"用例ID: {testcase_id}",
            f"接口: {testcase_data.get('interface_name', '')}",
            f"描述: {testcase_data.get('description', '')}",
        ]
        
        # 添加断言信息
        if "assertions" in testcase_data:
            assertions = testcase_data["assertions"]
            if assertions:
                assertion_types = [a.get("type", "") for a in assertions]
                parts.append(f"断言: {', '.join(assertion_types)}")
        
        return " | ".join(parts)
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()


# 全局向量数据库实例
_vector_db: Optional[VectorDB] = None


def get_vector_db(config: Optional[Dict[str, Any]] = None) -> VectorDB:
    """
    获取全局向量数据库实例（单例模式）
    
    Args:
        config: 配置字典（首次调用时必需）
        
    Returns:
        向量数据库实例
    """
    global _vector_db
    
    if _vector_db is None:
        if config is None:
            raise VectorDBError("首次调用必须提供配置")
        _vector_db = VectorDB(config)
    
    return _vector_db
