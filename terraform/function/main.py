import json
import mimetypes
import os
import urllib.error
import urllib.request

import functions_framework
import vertexai
from google.cloud import firestore
from vertexai.generative_models import (
    Content,
    FunctionDeclaration,
    GenerationConfig,
    GenerativeModel,
    Part,
    Tool,
)


PROJECT_ID = os.environ["PROJECT_ID"]
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "us-central1")
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "(default)")
RECIPES_COLLECTION = os.environ.get("RECIPES_COLLECTION", "recipes")
SESSIONS_COLLECTION = os.environ.get("SESSIONS_COLLECTION", "sessions")
TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
VISION_MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")
LANGUAGE = os.environ.get("LANGUAGE", "RU").upper()
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ALLOWED_CHATS = {
    chat_id.strip()
    for chat_id in os.environ.get("ALLOWED_CHATS", "").split(",")
    if chat_id.strip()
}

MAX_HISTORY_TURNS = 12

vertexai.init(project=PROJECT_ID, location=VERTEX_LOCATION)
db = firestore.Client(project=PROJECT_ID, database=FIRESTORE_DATABASE)


MESSAGES = {
    "RU": {
        "saved": 'Рецепт "{name}" (Теги: {tags}) успешно сохранен!',
        "save_err": "Ошибка: не передано имя или текст рецепта.",
        "not_found": "Рецепты по данному запросу не найдены.",
        "list_header": "Список рецептов в базе: \n- ",
        "updated": 'Рецепт "{name}" успешно обновлен!',
        "update_not_found": 'Ошибка: Рецепт "{name}" не найден. Сначала найди его точное название.',
        "update_err": "Ошибка: не передано имя или обновленный текст.",
        "unknown_op": "Неизвестная операция.",
        "db_err": "Ошибка БД: {err}",
        "cleared": "Память очищена! Готов к новому рецепту.",
        "vision_prompt": "Внимательно прочитай весь текст рецепта с этой картинки. Если это не рецепт, просто опиши.",
        "agent_prompt": (
            "Я сфотографировал рецепт. Текст:\n\n{text}\n\n"
            "Твоя задача: ВЫВЕДИ ЭТОТ ТЕКСТ В MARKDOWN И СПРОСИ МОЕГО "
            "РАЗРЕШЕНИЯ НА СОХРАНЕНИЕ. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО вызывать "
            "функции сохранения до моего подтверждения. Мой комментарий: {caption}."
        ),
        "error": "Ошибка в Cloud Function: {err}",
        "empty_response": "Не получилось сформировать ответ. Попробуй переформулировать запрос.",
        "tool_loop_limit": "Не получилось завершить операцию с базой рецептов. Попробуй еще раз.",
    },
    "EN": {
        "saved": 'Recipe "{name}" (Tags: {tags}) successfully saved!',
        "save_err": "Error: recipe name or content not provided.",
        "not_found": "No recipes found for this query.",
        "list_header": "List of recipes in the database: \n- ",
        "updated": 'Recipe "{name}" successfully updated!',
        "update_not_found": 'Error: Recipe "{name}" not found. Please search for its exact name first.',
        "update_err": "Error: recipe name or updated text not provided.",
        "unknown_op": "Unknown operation.",
        "db_err": "DB Error: {err}",
        "cleared": "Memory cleared! Ready for a new recipe.",
        "vision_prompt": "Carefully read all the recipe text from this image. If it is not a recipe, just describe what you see.",
        "agent_prompt": (
            "I took a photo of a recipe. Text:\n\n{text}\n\n"
            "Your task: FORMAT THIS TEXT AS MARKDOWN AND ASK FOR MY PERMISSION "
            "TO SAVE IT. IT IS STRICTLY FORBIDDEN to call save functions before "
            "I confirm. My comment: {caption}."
        ),
        "error": "Cloud Function error: {err}",
        "empty_response": "I could not generate a response. Please try rephrasing your request.",
        "tool_loop_limit": "I could not complete the recipe database operation. Please try again.",
    },
}


SYSTEM_INSTRUCTIONS = {
    "RU": """
Ты — умный и дружелюбный кулинарный ИИ-ассистент. Твоя единственная задача — помогать с рецептами: обсуждать идеи, улучшать рецепты, сохранять, искать и обновлять личную коллекцию.

Строго оставайся в кулинарном домене. Если запрос не связан с едой, рецептами или ингредиентами, вежливо откажи.

Критическое правило: запрещено вызывать save_recipe или update_recipe без явного подтверждения пользователя на конкретный текст рецепта.

Новый рецепт:
1. Не сохраняй сразу.
2. Преобразуй рецепт в чистый Markdown: заголовок, ингредиенты, шаги.
3. Покажи результат пользователю.
4. Спроси, нужно ли сохранить рецепт.
5. Вызывай save_recipe только после подтверждения.

Обновление рецепта:
1. Если нужно, сначала найди рецепт через search_recipes.
2. Сформируй полный обновленный текст.
3. Покажи его пользователю.
4. Спроси подтверждение.
5. Вызывай update_recipe только после подтверждения.

Поиск:
1. Используй search_recipes.
2. Для keyword передавай один корень главного слова в нижнем регистре.
3. Если рецепт найден, начинай ответ с "Из нашей книги рецептов:".
4. Если не найден, предложи вариант из своей памяти и предложи сохранить его.

Отвечай кратко, структурированно и на русском языке.
""",
    "EN": """
You are an intelligent and friendly AI culinary assistant. Your only goal is to help with recipes: discussing cooking ideas, improving recipes, and managing a personal recipe collection.

Stay strictly within the cooking domain. If a request is unrelated to food, recipes, or ingredients, politely refuse.

Critical rule: never call save_recipe or update_recipe without explicit user confirmation for the exact recipe text.

New recipe:
1. Do not save immediately.
2. Convert the recipe into clean Markdown: title, ingredients, steps.
3. Show the result to the user.
4. Ask whether it should be saved.
5. Call save_recipe only after confirmation.

Updating recipes:
1. If needed, search first with search_recipes.
2. Generate the full updated recipe text.
3. Show it to the user.
4. Ask for confirmation.
5. Call update_recipe only after confirmation.

Search:
1. Use search_recipes.
2. Pass exactly one lowercase keyword root.
3. If found, start with "From your recipe collection:".
4. If not found, suggest an answer from memory and offer to save it.

Answer concisely, with structure, in English.
""",
}


recipe_tool = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="save_recipe",
            description="Saves a recipe after explicit user confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "recipe_name": {"type": "string", "description": "Recipe title."},
                    "recipe_content": {"type": "string", "description": "Full recipe in Markdown."},
                    "tags": {"type": "string", "description": "Optional comma-separated recipe tags."},
                },
                "required": ["recipe_name", "recipe_content"],
            },
        ),
        FunctionDeclaration(
            name="search_recipes",
            description="Searches saved recipes by keyword, tags, and optional owner.",
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Single lowercase search root."},
                    "only_my": {"type": "string", "description": "Set to true to search only current user's recipes."},
                    "names_only": {"type": "string", "description": "Set to true to return only recipe names."},
                },
                "required": ["keyword"],
            },
        ),
        FunctionDeclaration(
            name="update_recipe",
            description="Updates an existing recipe after explicit user confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "recipe_name": {"type": "string", "description": "Exact recipe title."},
                    "new_content": {"type": "string", "description": "Full updated recipe in Markdown."},
                    "tags": {"type": "string", "description": "Optional updated tags."},
                },
                "required": ["recipe_name", "new_content"],
            },
        ),
    ]
)


def localized(key):
    return MESSAGES.get(LANGUAGE, MESSAGES["EN"])[key]


def recipe_id_from_name(recipe_name):
    return recipe_name.strip().lower().replace("/", "_")


def parse_bool(value):
    return str(value or "").strip().lower() == "true"


def recipes_ref():
    return db.collection(RECIPES_COLLECTION)


def sessions_ref():
    return db.collection(SESSIONS_COLLECTION)


def save_recipe(session_id, args):
    recipe_name = args.get("recipe_name")
    recipe_content = args.get("recipe_content")
    tags = args.get("tags") or ("No tags" if LANGUAGE == "EN" else "Без тегов")

    if not recipe_name or not recipe_content:
        return localized("save_err")

    recipe_id = recipe_id_from_name(recipe_name)
    recipes_ref().document(recipe_id).set(
        {
            "RecipeId": recipe_id,
            "OriginalName": recipe_name,
            "Content": recipe_content,
            "UserId": str(session_id),
            "Tags": tags,
        }
    )
    return localized("saved").format(name=recipe_name, tags=tags)


def search_recipes(session_id, args):
    keyword = str(args.get("keyword") or "").lower()
    only_my = parse_bool(args.get("only_my"))
    names_only = parse_bool(args.get("names_only"))
    matches = []

    for document in recipes_ref().stream():
        item = document.to_dict() or {}
        recipe_id = str(item.get("RecipeId") or document.id).lower()
        tags = str(item.get("Tags") or "").lower()

        if keyword and keyword not in recipe_id and keyword not in tags:
            continue

        if only_my and str(item.get("UserId")) != str(session_id):
            continue

        matches.append(item)

    if not matches:
        return localized("not_found")

    if names_only:
        names = [item.get("OriginalName") or item.get("RecipeId") for item in matches]
        return localized("list_header") + "\n- ".join(names)

    result = [
        {
            "name": item.get("OriginalName") or item.get("RecipeId"),
            "tags": item.get("Tags", ""),
            "recipe": item.get("Content", "..."),
        }
        for item in matches[:5]
    ]
    return json.dumps(result, ensure_ascii=False)


def update_recipe(args):
    recipe_name = args.get("recipe_name")
    new_content = args.get("new_content")
    new_tags = args.get("tags")

    if not recipe_name or not new_content:
        return localized("update_err")

    recipe_id = recipe_id_from_name(recipe_name)
    doc_ref = recipes_ref().document(recipe_id)
    snapshot = doc_ref.get()

    if not snapshot.exists:
        return localized("update_not_found").format(name=recipe_name)

    current = snapshot.to_dict() or {}
    update_data = {"Content": new_content}
    if new_tags and str(new_tags).strip():
        update_data["Tags"] = new_tags

    doc_ref.update(update_data)
    return localized("updated").format(name=current.get("OriginalName", recipe_name))


def execute_tool(function_name, args, session_id):
    try:
        if function_name == "save_recipe":
            return save_recipe(session_id, args)
        if function_name == "search_recipes":
            return search_recipes(session_id, args)
        if function_name == "update_recipe":
            return update_recipe(args)
        return localized("unknown_op")
    except Exception as exc:
        print("Firestore error:", exc)
        return localized("db_err").format(err=str(exc))


def response_text(response):
    chunks = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)

    if chunks:
        return "\n".join(chunks).strip()

    try:
        return response.text.strip()
    except Exception:
        return ""


def response_function_calls(response):
    calls = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            function_call = getattr(part, "function_call", None)
            if getattr(function_call, "name", None):
                calls.append(function_call)
    return calls


def load_history(chat_id):
    snapshot = sessions_ref().document(str(chat_id)).get()
    if not snapshot.exists:
        return []

    raw_history = (snapshot.to_dict() or {}).get("history", [])[-MAX_HISTORY_TURNS:]
    contents = []
    for turn in raw_history:
        role = turn.get("role")
        text = turn.get("text")
        if role in {"user", "model"} and text:
            contents.append(Content(role=role, parts=[Part.from_text(text)]))
    return contents


def save_history(chat_id, user_text, model_text):
    doc_ref = sessions_ref().document(str(chat_id))
    snapshot = doc_ref.get()
    history = []
    if snapshot.exists:
        history = (snapshot.to_dict() or {}).get("history", [])

    history.extend(
        [
            {"role": "user", "text": user_text},
            {"role": "model", "text": model_text},
        ]
    )

    doc_ref.set(
        {
            "history": history[-MAX_HISTORY_TURNS:],
            "updatedAt": firestore.SERVER_TIMESTAMP,
        }
    )


def clear_history(chat_id):
    sessions_ref().document(str(chat_id)).delete()


def build_agent_model():
    instruction = SYSTEM_INSTRUCTIONS.get(LANGUAGE, SYSTEM_INSTRUCTIONS["EN"])
    return GenerativeModel(TEXT_MODEL, system_instruction=instruction)


def run_agent(chat_id, input_text):
    model = build_agent_model()
    contents = load_history(chat_id)
    contents.append(Content(role="user", parts=[Part.from_text(input_text)]))

    for _ in range(4):
        response = model.generate_content(
            contents,
            generation_config=GenerationConfig(
                temperature=0.4,
                max_output_tokens=4096,
            ),
            tools=[recipe_tool],
        )
        calls = response_function_calls(response)

        if not calls:
            answer = response_text(response) or localized("empty_response")
            save_history(chat_id, input_text, answer)
            return answer

        contents.append(response.candidates[0].content)
        function_response_parts = []
        for call in calls:
            args = {key: value for key, value in call.args.items()}
            result = execute_tool(call.name, args, chat_id)
            function_response_parts.append(
                Part.from_function_response(
                    name=call.name,
                    response={"content": result},
                )
            )
        contents.append(Content(parts=function_response_parts))

    answer = localized("tool_loop_limit")
    save_history(chat_id, input_text, answer)
    return answer


def telegram_request(method, payload=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    data = None
    headers = {}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def split_message(text, limit=3900):
    text = text or ""
    return [text[index : index + limit] for index in range(0, len(text), limit)] or [""]


def send_message(chat_id, text):
    if not text or not text.strip():
        print("Attempted to send an empty Telegram message. Skipping.")
        return

    for chunk in split_message(text):
        telegram_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": chunk,
            },
        )


def download_telegram_photo(photo_sizes):
    file_id = photo_sizes[-1]["file_id"]
    file_data = telegram_request(f"getFile?file_id={file_id}")
    file_path = file_data["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

    with urllib.request.urlopen(file_url, timeout=30) as response:
        image_bytes = response.read()

    mime_type, _ = mimetypes.guess_type(file_path)
    return image_bytes, mime_type or "image/jpeg"


def extract_text_from_image(image_bytes, mime_type):
    model = GenerativeModel(VISION_MODEL)
    image = Part.from_data(data=image_bytes, mime_type=mime_type)
    response = model.generate_content(
        [image, localized("vision_prompt")],
        generation_config=GenerationConfig(
            temperature=0.1,
            max_output_tokens=2048,
        ),
    )
    return response_text(response)


@functions_framework.http
def telegram_webhook(request):
    if request.method == "GET":
        return ("OK", 200)

    try:
        body = request.get_json(silent=True) or {}
        message = body.get("message")
        if not message:
            return ("OK", 200)

        chat_id = str(message["chat"]["id"])
        if chat_id not in ALLOWED_CHATS:
            print(f"Access denied for chat: {chat_id}")
            return ("OK", 200)

        user_text = message.get("text", "")
        photo = message.get("photo")
        caption = message.get("caption", "")

        if user_text.strip() == "/new":
            clear_history(chat_id)
            send_message(chat_id, localized("cleared"))
            return ("OK", 200)

        if photo:
            image_bytes, mime_type = download_telegram_photo(photo)
            extracted_text = extract_text_from_image(image_bytes, mime_type)
            agent_prompt = localized("agent_prompt").format(
                text=extracted_text,
                caption=caption,
            )
            answer = run_agent(chat_id, agent_prompt)
            send_message(chat_id, answer)
            return ("OK", 200)

        if user_text:
            answer = run_agent(chat_id, user_text)
            send_message(chat_id, answer)

    except urllib.error.URLError as exc:
        print("Telegram API error:", exc)
    except Exception as exc:
        print("Cloud Function error:", exc)
        try:
            body = request.get_json(silent=True) or {}
            chat_id = str(body.get("message", {}).get("chat", {}).get("id", ""))
            if chat_id:
                send_message(chat_id, localized("error").format(err=str(exc)))
        except Exception as nested_exc:
            print("Failed to report error to Telegram:", nested_exc)

    return ("OK", 200)
