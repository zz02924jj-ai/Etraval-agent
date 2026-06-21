# Etraval-agent — 智能旅行助手系统 v3.0

基于 Agent-to-Agent (A2A) 协议的多智能体旅行助手系统。

## 架构

```
用户输入 → 意图识别 → A2A Router
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
  天气查询Agent     票务查询Agent         景点介绍Agent
   (GLM-4-32B)    (react 模式)         (联网+知识库+评价)
        │                   │                   │
        ▼                   ▼                   ▼
  天气 MCP Server   票务 MCP Server      知识检索 MCP Server
  (和风天气API)    (携程/12306/大麦)    (Milvus + bge-m3)
                                    ▲
                                    │
                            多模态视觉Agent
                            (GLM-4V-9B + PaddleOCR)
```

## 关键技术栈

- A2A 协议：python-a2a (扩展)
- LLM：GLM-4-32B, GLM-4V-9B
- MCP：FastMCP
- 向量库：Milvus + bge-m3
- OCR：PaddleOCR
- 后端：FastAPI + LangChain
- 前端：Vue 3 + Tailwind CSS

## 源自 SmartVoyage

本项目基于 SmartVoyage v2.0 二次开发，继承其 A2A/MCP 架构设计。
