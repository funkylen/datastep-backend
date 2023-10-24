from langchain.prompts.prompt import PromptTemplate
from langchain.chains import LLMChain
from langchain.chat_models import ChatOpenAI

from datastep.components.datastep_sql_database import DatastepSqlDatabase

similar_queries_template = """По данной схеме таблицы и составь 4 похожих вопроса на данный.

Вопрос:
{input}

Схема таблицы:
{table_info}

Перечисли вопросы через запятую
"""


def get_chain():
    similar_queries_prompt = PromptTemplate(
        template=similar_queries_template,
        input_variables=["table_info", "input"]
    )
    llm = ChatOpenAI(temperature=0.8, verbose=False, model_name="gpt-3.5-turbo")
    similar_queries_chain = LLMChain(llm=llm, prompt=similar_queries_prompt, verbose=False)
    return similar_queries_chain


def parse_similar_queries(similar_queries: str) -> list[str]:
    return [q[3:] for q in similar_queries.split("\n")]


def generate_similar_queries(input: str, database: DatastepSqlDatabase) -> list[str]:
    similar_queries_chain = get_chain()
    response = similar_queries_chain.run(
        input=input,
        table_info=database.database.get_table_info()
    )

    return parse_similar_queries(response)
