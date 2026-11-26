# Vorlagen

- `datei.md`: Inhalt jeder neuen Markdown-Datei. `{{title}}` wird durch den
  Dateinamen ohne Endung ersetzt, `{{date}}` durch das heutige Datum.
- `ordner.yaml`: Inhalt der `.pandora.yaml` in jedem neuen Ordner.

Änderungen gelten ab dem nächsten Start von mdtool. Wurde mdtool ohne
`--editable` installiert, muss es danach neu installiert werden.
