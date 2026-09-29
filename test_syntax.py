import py_compile

try:
    py_compile.compile(
        "bybit_api.py",
        doraise=True
    )

    print("✅ bybit_api.py syntax and indentation are correct.")

except py_compile.PyCompileError as e:
    print("❌ Syntax error found:")
    print(e)