import json
import os
from chatbot import (
    OPENAI_API_KEY,
    MIREYE_API_TOKEN,
    SYSTEM_PROMPT,
    TOOLS,
    execute_tool_call,
    _check_keys,
)
from openai import OpenAI

def ask_question(client: OpenAI, user_input: str):
    print(f"\n" + "="*70)
    print(f"USER: {user_input}")
    print("="*70)
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input}
    ]
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
    )
    
    assistant_message = response.choices[0].message
    
    # Handle tool calls
    while assistant_message.tool_calls:
        messages.append(assistant_message.model_dump())
        
        for tool_call in assistant_message.tool_calls:
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)
            print(f"-> [TOOL CALLED]: {func_name}({json.dumps(func_args)})")
            
            result = execute_tool_call(func_name, func_args)
            
            # Print a snippet of tool output
            snippet = result[:150] + "..." if len(result) > 150 else result
            print(f"<- [TOOL RESULT PREVIEW]: {snippet}")
            
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })
            
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        assistant_message = response.choices[0].message
        
    reply = assistant_message.content or "(No response)"
    print(f"\nASSISTANT:\n{reply}\n")

if __name__ == "__main__":
    _check_keys()
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    test_questions = [
        "What is the difference between synchronous and asynchronous programming in two sentences?",
        "What is the flood risk around Galveston, Texas?",
        "What is the elevation and slope in Aspen, Colorado?",
        "What is the wildfire risk around South Lake Tahoe, California?",
        "Tell me a short fun fact about space."
    ]
    
    for i, q in enumerate(test_questions, 1):
        print(f"\n--- TEST {i}/5 ---")
        ask_question(client, q)
