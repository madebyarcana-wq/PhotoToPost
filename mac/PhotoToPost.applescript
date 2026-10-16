-- PhotoToPost のドロップ用アプリ（setup.command が __REPO__ を置き換えて作成する）
property repoDir : "__REPO__"

-- アイコンをダブルクリックしたとき：フォルダを選ぶ画面を出す
on run
	set theFolder to choose folder with prompt "投稿用にする写真フォルダを選んでください"
	processFolders({theFolder})
end run

-- フォルダをアイコンにドロップしたとき
on open theItems
	processFolders(theItems)
end open

on processFolders(theItems)
	set choice to button returned of (display dialog "写真フォルダを処理します。" & return & "初めてのときは「3件だけ試す」がおすすめです。" buttons {"キャンセル", "3件だけ試す", "すべて処理"} default button "すべて処理" cancel button "キャンセル" with title "PhotoToPost")
	set opts to ""
	if choice is "3件だけ試す" then set opts to " --limit 3"
	repeat with anItem in theItems
		set folderPath to POSIX path of anItem
		set cmd to (quoted form of (repoDir & "/mac/run.sh")) & " " & (quoted form of folderPath) & opts
		tell application "Terminal"
			activate
			do script cmd
		end tell
	end repeat
end processFolders
