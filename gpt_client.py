import openai
import regex as re
import os
from timeout_function_decorator.timeout_decorator import timeout
from tiktoken import encoding_for_model

MAX_MODEL_TOKENS = 4096  # max tokens the model can handle
MAX_RESPONSE_TOKENS = 250  # max tokens in response
# TODO move temperature to personas
TEMPERATURE = 0.7  # between 0 and 2. Higher => more random, lower => more deterministic.
MAX_CHUNK_SIZE = 100
# MODEL = "gpt-3.5-turbo"
MODEL = "gpt-4"

APP_RULES = [
    "Do your best to give me responses in less than 40 words.",
    "You understand all languages",
    "I am communicating with you through a speech to text engine which may not always hear me correctly. Adjust for "
    "this, but don't tell me you're adjusting.",
    "If a query appears nonsensical, likely due to speech-to-text errors or ambient noise, respond with '-1' to "
    "indicate the issue and include no other text."
    "In such a case, it is possible you are hearing me talking to someone else.",
    "Be aware that I will be using a speech-to-text engine that may not always be accurate.",
    "If I make a spelling mistake, don't point it out.",
    "Also, prompt me occasionally with relevant or interesting questions to foster a two-way conversation",
    "I will sometimes use the NATO phonetic alphabet.",
]


def count_tokens(text):
    encoding = encoding_for_model(MODEL)
    return len(encoding.encode(text))


class GptClient:
    def __init__(self, personality_rules):
        openai.api_key = os.getenv("OPENAI_API_KEY")
        # TODO load from disk
        self.conversation = [
            {"role": "system",
             "content": " ".join(personality_rules + APP_RULES)},
        ]
        self.total_tokens = count_tokens(self.conversation[-1]['content'])

    @timeout(15)
    def get_response(self, message):
        self.conversation.append({
            "role": "user",
            "content": message,
        })
        self.total_tokens += count_tokens(message)

        # make sure there is room for a response
        while self.total_tokens > MAX_MODEL_TOKENS - MAX_RESPONSE_TOKENS:
            removed_message = self.conversation.pop(1)  # don't remove the system message
            self.total_tokens = count_tokens(removed_message['content'])

        chat = openai.ChatCompletion.create(
            model=MODEL,
            messages=self.conversation,
            temperature=TEMPERATURE,
            max_tokens=MAX_RESPONSE_TOKENS
        )
        response = chat.choices[0].message.content
        self.total_tokens += count_tokens(response)

        self.conversation.append({
            "role": "assistant",
            "content": response
        })

        return response

    @timeout(8)
    def get_response_generator(self, message):
        self.conversation.append({
            "role": "user",
            "content": message,
        })
        self.total_tokens += count_tokens(message)

        # make sure there is room for a response
        while self.total_tokens > MAX_MODEL_TOKENS - MAX_RESPONSE_TOKENS:
            removed_message = self.conversation.pop(1)  # don't remove the system message
            self.total_tokens = count_tokens(removed_message['content'])

        sentence_buffer = []
        response = ""
        content = ""
        for chunk in openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=self.conversation,
                temperature=TEMPERATURE,
                max_tokens=MAX_RESPONSE_TOKENS,
                stream=True
        ):
            content_gen = chunk["choices"][0].get("delta", {}).get("content")
            if content_gen is not None:
                content = ''.join(content_gen)
                sentence_buffer.append(content)

                # Check if the buffer contains a full sentence
                # TODO this regex would work better except for the last iteration. Since we're dealing with a
                # TODO generator, we can't know if it's the end of the string. chars appear one by one.
                # if re.match(r"[\.?!]\B", content) or content_gen:
                if any(char in '.!?\n' for char in content):  # TODO end of sentence AND not a short sentence
                    sentence_chunk = ''.join(sentence_buffer)

                    response += sentence_chunk
                    print(f'\t"{sentence_chunk.strip()}"')
                    yield sentence_chunk
                    sentence_buffer = []
                    content = ""
        if content and content not in ["1", "-1"]:  # anything left over that wasn't identified as a sentence
            print(f'\t"{content}"')
            response += content
            yield content
        yield None

        self.total_tokens += count_tokens(response)
        self.conversation.append({
            "role": "assistant",
            "content": response
        })
        # TODO last response to disk
