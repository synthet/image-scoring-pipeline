import gradio as gr

def update(val):
    if val == "dict_zero":
        return {"General Score": 0.0}
    elif val == "dict_val":
        return {"General Score": 0.65}
    elif val == "float_zero":
        return 0.0
    elif val == "float_val":
        return 0.65
    elif val == "empty":
        return {}
    elif val == "none":
        return None

with gr.Blocks() as demo:
    gr.Markdown("Test Label Component")
    with gr.Row():
        btn_dict_zero = gr.Button("Dict Zero")
        btn_dict_val = gr.Button("Dict Val")
        btn_float_zero = gr.Button("Float Zero")
        btn_float_val = gr.Button("Float Val")
        btn_empty = gr.Button("Empty")
        btn_none = gr.Button("None")
    
    lbl = gr.Label(label="Output", num_top_classes=1)
    
    btn_dict_zero.click(fn=lambda: update("dict_zero"), outputs=lbl)
    btn_dict_val.click(fn=lambda: update("dict_val"), outputs=lbl)
    btn_float_zero.click(fn=lambda: update("float_zero"), outputs=lbl)
    btn_float_val.click(fn=lambda: update("float_val"), outputs=lbl)
    btn_empty.click(fn=lambda: update("empty"), outputs=lbl)
    btn_none.click(fn=lambda: update("none"), outputs=lbl)

if __name__ == "__main__":
    demo.launch(server_port=7861, prevent_thread_lock=True)
    print("Launched on 7861")
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping")
