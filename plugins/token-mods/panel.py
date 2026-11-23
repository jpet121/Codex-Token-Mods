"""Local control panel for Codex token tools. Uses Python's Tk desktop UI."""
import json
import time
import tkinter as tk
from tkinter import ttk
from store import NAMES, active, database, report, get, put


def main():
    root = tk.Tk()
    root.title("Codex token tools")
    frame = ttk.Frame(root, padding=14)
    frame.pack(fill="both", expand=True)
    switches = {}
    session = tk.StringVar()
    summary = tk.StringVar()
    db = database(persistent=True)

    def toggle(name):
        with db:
            db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)",(name,switches[name].get()))

    for i, name in enumerate(NAMES):
        switches[name] = tk.IntVar(value=int(name in active(db)))
        ttk.Checkbutton(frame,text=name,variable=switches[name],
                        command=lambda n=name:toggle(n)).grid(row=i//3,column=i%3,sticky="w",padx=5)
    ttk.Label(frame,text="Session").grid(row=3,column=0,sticky="w")
    sessions = ttk.Combobox(frame,textvariable=session,state="readonly",width=40)
    sessions.grid(row=3,column=1,columnspan=2,sticky="ew")
    ttk.Label(frame,textvariable=summary,justify="left").grid(row=4,column=0,columnspan=3,sticky="w",pady=10)
    text = tk.Text(frame,height=12,width=75,wrap="word")
    text.grid(row=8,column=0,columnspan=3,sticky="nsew")
    from tools_api import configure
    option=tk.StringVar(value='input_file'); value=tk.StringVar(value='true')
    chooser=ttk.Combobox(frame,textvariable=option,values=tuple(__import__('store').DEFAULTS),width=24,state='readonly')
    chooser.grid(row=6,column=0,sticky='ew')
    ttk.Entry(frame,textvariable=value,width=35).grid(row=6,column=1,sticky='ew')
    def save_option():
        try:
            try: parsed=json.loads(value.get())
            except ValueError: parsed=value.get()
            with db: result=configure(db,dict(action='set',name=option.get(),value=parsed))
            text.delete('1.0','end'); text.insert('end',json.dumps(result,indent=2))
        except ValueError as error: text.delete('1.0','end'); text.insert('end',str(error))
    ttk.Button(frame,text='Save option',command=save_option).grid(row=6,column=2)
    def details():
        from insights import inventory
        text.delete('1.0','end'); text.insert('end',json.dumps(dict(plugins=inventory(),usage=report(db,session.get())),ensure_ascii=False,indent=2))
    ttk.Button(frame,text='Inventory and module usage',command=details).grid(row=7,column=0,columnspan=2,sticky='w')
    def hidden():
        module=selected_module.get()
        with db: put(db,module+':hidden',not bool(get(db,module+':hidden')))
    selected_module=tk.StringVar(value='effort-optimizer')
    ttk.Combobox(frame,textvariable=selected_module,values=NAMES,state='readonly').grid(row=9,column=0)
    ttk.Button(frame,text='Toggle advice visibility',command=hidden).grid(row=9,column=1)

    def handoff():
        from tools_api import handoff as prepare
        try:
            with db: result=prepare(db,dict(session=session.get()))
        except ValueError as error:
            summary.set(str(error)); return
        text.delete("1.0","end")
        text.insert("end",result['text'])

    ttk.Button(frame,text="Load handoff",command=handoff).grid(row=5,column=0,sticky="w")
    def copy():
        root.clipboard_clear()
        root.clipboard_append(text.get("1.0","end-1c"))
    ttk.Button(frame,text="Copy text",command=copy).grid(row=5,column=1,sticky="w")

    def refresh():
        ids=[r[0] for r in db.execute("SELECT session FROM turns UNION SELECT session FROM requests UNION SELECT session FROM activity")]
        sessions["values"]=ids
        if not session.get() and ids:
            session.set(ids[0])
        stats=report(db,session.get())
        row=db.execute("SELECT observed FROM activity WHERE session=?",(session.get(),)).fetchone()
        age=f"{int(time.time()-row[0])} seconds" if row else "unknown"
        summary.set(f"Time since last observed request: {age}; cache expiry unknown\nMeasured tokens: {json.dumps(stats['measured_tokens'])}\nAttempts without counts: {stats['attempts_without_counts']}; keepwarm disabled")
        for name, variable in switches.items(): variable.set(int(name in active(db)))
        root.after(3000,refresh)
    refresh()
    try:
        root.mainloop()
    finally:
        db.close()

if __name__ == "__main__":
    main()
