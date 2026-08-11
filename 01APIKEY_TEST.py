from openai import OpenAI
import os

client = OpenAI(
    # 如果没有配置环境变量，请用阿里云百炼API Key替换：api_key="sk-xxx"

    # base_url="https://ws-wibk6xl3op0zm1sx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    base_url="https://ws-wibk6xl3op0zm1sx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
)

# messages = [{"role": "user", "content": "你是谁"},{"role": "system", "content": "you are a helpful assistant"}]
completion = client.chat.completions.create( # type: ignore
    model="qwen3.8-max",  # 您可以按需更换为其它深度思考模型
    messages=[{"role": "system", "content": "you are a helpful assistant"},
              {"role": "user", "content": "你是谁"}, ],
    extra_body={"enable_thinking": True},
    stream=True,
)


is_answering = False  # 是否进入回复阶段
print("\n" + "=" * 20 + "思考过程" + "=" * 20)
for chunk in completion:
    if not chunk.choices:
        continue
    delta = chunk.choices[0].delta
    if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
        if not is_answering:
            print(delta.reasoning_content, end="", flush=True)
    if hasattr(delta, "content") and delta.content:
        if not is_answering:
            print("\n" + "=" * 20 + "完整回复" + "=" * 20)
            is_answering = True
        print(delta.content, end="", flush=True)
