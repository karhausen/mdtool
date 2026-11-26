# Vorlagen

- `datei.md`: Inhalt jeder neuen Markdown-Datei. `{{title}}` wird durch den
  Dateinamen ohne Endung ersetzt, `{{date}}` durch das heutige Datum.
- `ordner.yaml`: Inhalt der `.policy.yaml` in jedem neuen Ordner.

Diese Dateien sind die Standardvorlagen. Eigene Vorlagen gehören nach
`~/.config/mdtool/templates/`. Dorthin kopiert `mdtool --vorlagen` die
Standardvorlagen, ohne Vorhandenes zu überschreiben. Liegt dort eine Datei,
gilt sie statt der Standardvorlage.
