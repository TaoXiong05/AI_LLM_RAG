from urllib import response

from openai import OpenAI

# 1. get client object
client = OpenAI(
    base_url="https://ws-wibk6xl3op0zm1sx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
)

# 2 调用模型
response = client.chat.completions.create(  # type: ignore
    model="qwen3.8-max",  # 您可以按需更换为其它深度思考模型
    messages=[{"role": "system", "content": "你是一个python编程专家"},# type: ignore
              {"role": "assistant", "content": "你是一个python编程专家"},
              {"role": "user", "content": "输出1-100的数字 python code"}],

)

print(response.choices[0].message.content)
