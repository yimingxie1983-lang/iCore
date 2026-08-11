

import aiosqlite
from pathlib import Path

from cancer_claw.config import settings
from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

def _default_scratch_db() -> str:

    data_dir = Path(settings.paths.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "agent_scratch.db")

class DbOpsTool(BaseTool):


    @property
    def name(self) -> str:
        return "db_ops"

    @property
    def description(self) -> str:
        return "执行 SQL 查询和写操作。默认操作 iCore 的 SQLite 数据库，也可指定外部数据库文件。"

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "db_ops",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["query_sql", "execute_sql"],
                            "description": "操作类型：query_sql 查询 / execute_sql 写入"
                        },
                        "sql": {
                            "type": "string",
                            "description": "SQL 语句"
                        },
                        "params": {
                            "type": "array",
                            "items": {},
                            "description": "SQL 参数列表（用 ? 占位符）"
                        },
                        "db_path": {
                            "type": "string",
                            "description": "SQLite 数据库文件路径（可选，默认使用独立的暂存库 agent_scratch.db；不会也不能操作框架生产主库）"
                        },
                    },
                    "required": ["action", "sql"]
                }
            }
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")
        sql = kwargs.get("sql", "")
        params = kwargs.get("params", [])

        db_path = kwargs.get("db_path", "") or _default_scratch_db()

        if not sql.strip():
            return ToolResult(success=False, error="sql 参数不能为空")

        try:
            if action == "query_sql":
                return await self._query(db_path, sql, params)
            elif action == "execute_sql":
                return await self._execute(db_path, sql, params)
            else:
                return ToolResult(success=False, error=f"不支持的操作: {action}")
        except Exception as e:
            return ToolResult(success=False, error=f"SQL 执行失败: {str(e)}")

    async def _query(self, db_path: str, sql: str, params: list) -> ToolResult:

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()

            if not rows:
                return ToolResult(success=True, output="查询结果为空（0 行）", data={"rows": [], "count": 0})


            columns = [desc[0] for desc in cursor.description]


            max_rows = 100
            result_rows = []
            for row in rows[:max_rows]:
                result_rows.append(dict(row))


            header = " | ".join(columns)
            separator = "-" * len(header)
            lines = [header, separator]
            for row_dict in result_rows:
                line = " | ".join(str(row_dict.get(col, "")) for col in columns)
                lines.append(line)

            if len(rows) > max_rows:
                lines.append(f"... 共 {len(rows)} 行，只显示前 {max_rows} 行")

            return ToolResult(
                success=True,
                output="\n".join(lines),
                data={"rows": result_rows, "count": len(rows), "columns": columns},
            )

    async def _execute(self, db_path: str, sql: str, params: list) -> ToolResult:

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(sql, params)
            await db.commit()
            return ToolResult(
                success=True,
                output=f"SQL 执行成功，影响 {cursor.rowcount} 行",
                data={"rowcount": cursor.rowcount},
            )
