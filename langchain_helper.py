from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceInstructEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
import os
import pandas as pd
from langchain_core.documents import Document
import re

load_dotenv()

llm = ChatGoogleGenerativeAI(model="gemini-pro", temperature=0.1, google_api_key=os.environ["GOOGLE_API_KEY"])

instructor_embeddings = HuggingFaceInstructEmbeddings(model_name="hkunlp/instructor-large",
                                                      model_kwargs={'device': 'cpu'},
                                                      encode_kwargs={'normalize_embeddings': True},
                                                      query_instruction="Represent the query for retrieval: ")
vectordb_file_path = "faiss-index"


def load_excel(file_path):
    df = pd.read_excel(file_path)
    documents = []
    for index, row in df.iterrows():
        content = f"Question: {row['prompt']}\nAnswer: {row['response']}"
        doc = Document(page_content=content, metadata={"source": file_path, "row": index})
        documents.append(doc)
    return documents


def create_vector_db():
    data = load_excel("bank_faq.xlsx")
    vectordb = FAISS.from_documents(documents=data, embedding=instructor_embeddings)
    vectordb.save_local(folder_path=vectordb_file_path)


def get_qa_chain():
    vectordb = FAISS.load_local(folder_path=vectordb_file_path, embeddings=instructor_embeddings,
                                allow_dangerous_deserialization=True)

    # retriever = vectordb.as_retriever()  # A retriever takes the query as input and looks for relevant documents in

    # the vector database using cosine similarity matching

    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)

    def create_manual_prompt(inputs):
        context = inputs["context"]
        question = inputs["question"]
        manual_prompt = (f"Based on the following context, please answer the questions below. \n\nContext:\n{context}"
                         f"\n\nQuestion: {question}\n\nPlease provide a detailed explanation in your response.In the "
                         f"answer try to provide as much text as possible from 'response' section in the source "
                         f"document context without making much changes.")
        return manual_prompt

    def extract_answer(raw_response):
        match = re.search(r'\*\*Answer:\*\*(.*)', raw_response, re.DOTALL)
        if match:
            return match.group(1).strip()
        return raw_response  # Return the full response if no **Answer:** is found

    chain = (
            {
                "context": vectordb.as_retriever() | format_docs,
                "question": RunnablePassthrough(),
            }
            | RunnablePassthrough.assign(prompt=create_manual_prompt)
            | (lambda x: x["prompt"])
            | llm
            | StrOutputParser()
            | extract_answer
    )
    return chain


if __name__ == "__main__":
    qa_chain = get_qa_chain()
    response = qa_chain.invoke("i forgot my password")
    print(response)
