"use client";

import { BlockNoteEditor } from "@blocknote/core";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";
import { useCallback, useState } from "react";
import styles from "./CollaborativeEditor.module.css";
import { MoonIcon, SunIcon } from "@/icons";
import { Button } from "@/primitives/Button";

export type EditorProps = {
  doc: any;
  provider: any;
  /**
   * The room name must be a valid UUID v4 for the current backend.
   */
  roomName: string;
};

export default function BlockNote({ doc, provider, roomName }: EditorProps) {
  // Provide static user info
  const userInfo = { name: "Demo User", color: "#00bcd4" };

  const editor: BlockNoteEditor = useCreateBlockNote({
    collaboration: {
      provider,
      fragment: doc.getXmlFragment("document-store"),
      user: userInfo,
    },
  });

  const [theme, setTheme] = useState<"light" | "dark">("light");

  const changeTheme = useCallback(() => {
    const newTheme = theme === "light" ? "dark" : "light";
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-theme", newTheme);
    }
    setTheme(newTheme);
  }, [theme]);

  return (
    <div className={styles.container}>
      <div className={styles.editorHeader}>
        <div style={{ flex: 1, textAlign: 'left', fontWeight: 'bold', fontSize: '1.1rem' }}>
          Room: {roomName}
        </div>
        <Button
          className={styles.button}
          variant="subtle"
          onClick={changeTheme}
          aria-label="Switch Theme"
        >
          {theme === "dark" ? (
            <SunIcon style={{ width: "18px" }} />
          ) : (
            <MoonIcon style={{ width: "18px" }} />
          )}
        </Button>
      </div>
      <div className={styles.editorPanel}>
        <BlockNoteView
          editor={editor}
          className={styles.editorContainer}
          theme={theme}
        />
      </div>
    </div>
  );
}
