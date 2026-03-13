Attribute VB_Name = "modNormalRefresh"
Option Explicit

Private Function GetMonthStarts(ws As Worksheet) As Collection
    Dim col As Long
    Dim starts As New Collection
    For col = 1 To 227
        If InStr(1, CStr(ws.Cells(3, col).Value), "년", vbTextCompare) > 0 And InStr(1, CStr(ws.Cells(3, col).Value), "월", vbTextCompare) > 0 Then
            starts.Add col
        End If
    Next col
    Set GetMonthStarts = starts
End Function

Private Function GetBlockStarts(ws As Worksheet) As Collection
    Dim r As Long
    Dim starts As New Collection
    For r = 6 To 95
        If CStr(ws.Cells(r, 2).Value) = "전  체" Or Left$(CStr(ws.Cells(r, 2).Value), 3) = "청호_" Then
            starts.Add r
        End If
    Next r
    Set GetBlockStarts = starts
End Function

Private Function GetDayCols(ws As Worksheet, startCol As Long) As Collection
    Dim cols As New Collection
    Dim c As Long
    c = startCol
    Do While c <= 227
        If InStr(1, CStr(ws.Cells(4, c).Value), "-", vbTextCompare) > 0 Then
            cols.Add c
            c = c + 1
        Else
            Exit Do
        End If
    Loop
    Set GetDayCols = cols
End Function

Private Function GetMonthTotalCol(ws As Worksheet, startCol As Long) As Long
    Dim c As Long
    For c = startCol To 227
        If CStr(ws.Cells(5, c).Value) = "계" Then
            GetMonthTotalCol = c
            Exit Function
        End If
    Next c
    GetMonthTotalCol = 227
End Function

Private Function MakeKey(ByVal d As String, ByVal center As String) As String
    MakeKey = d & "|" & center
End Function

Private Sub AddCounts(dict As Object, ByVal d As String, ByVal center As String, ByVal prod As String)
    Dim key As String
    Dim arr As Variant

    key = MakeKey(d, center)
    If Not dict.Exists(key) Then
        dict.Add key, Array(0&, 0&, 0&, 0&) ' mat, fou, fra, pan
    End If

    arr = dict(key)
    If InStr(1, prod, "매트", vbTextCompare) > 0 Then arr(0) = CLng(arr(0)) + 1
    If InStr(1, prod, "파운", vbTextCompare) > 0 Then arr(1) = CLng(arr(1)) + 1
    If InStr(1, prod, "프레", vbTextCompare) > 0 Then arr(2) = CLng(arr(2)) + 1
    If InStr(1, prod, "판", vbTextCompare) > 0 Then arr(3) = CLng(arr(3)) + 1
    dict(key) = arr
End Sub

Private Function GetCounts(dict As Object, ByVal d As String, ByVal center As String) As Variant
    Dim key As String
    key = MakeKey(d, center)
    If dict.Exists(key) Then
        GetCounts = dict(key)
    Else
        GetCounts = Array(0&, 0&, 0&, 0&)
    End If
End Function

Public Sub RefreshNormalSheet()
    Dim wsData As Worksheet, wsRpt As Worksheet
    Dim dict As Object
    Dim monthStarts As Collection, blockStarts As Collection, dayCols As Collection
    Dim lastRow As Long, r As Long
    Dim d As String, center As String, prod As String
    Dim bs As Variant, ms As Variant, dc As Variant
    Dim arr As Variant
    Dim rowTotal As Long, rowMat As Long, rowFou As Long, rowFra As Long, rowPan As Long
    Dim rowCumTotal As Long, rowCumMat As Long, rowCumFou As Long, rowCumFra As Long, rowCumPan As Long
    Dim runTotal As Long, runMat As Long, runFou As Long, runFra As Long, runPan As Long
    Dim vMat As Long, vFou As Long, vFra As Long, vPan As Long, vTotal As Long
    Dim lastMonthTotalCol As Long, monthTotalCol As Long
    Dim overallFinal As Double

    Set wsData = ThisWorkbook.Worksheets("출고자료")
    Set wsRpt = ThisWorkbook.Worksheets("정상")

    Application.ScreenUpdating = False
    Application.EnableEvents = False
    Application.Calculation = xlCalculationManual

    Set dict = CreateObject("Scripting.Dictionary")

    lastRow = wsData.Cells(wsData.Rows.Count, 1).End(xlUp).Row
    For r = 2 To lastRow
        If wsData.Rows(r).Hidden = False Then
            d = Trim$(CStr(wsData.Cells(r, 9).Text))
            center = Trim$(CStr(wsData.Cells(r, 13).Text))
            prod = Trim$(CStr(wsData.Cells(r, 18).Text))

            If Len(d) > 0 Then
                AddCounts dict, d, "ALL", prod
                If Len(center) > 0 Then
                    AddCounts dict, d, center, prod
                End If
            End If
        End If
    Next r

    Set monthStarts = GetMonthStarts(wsRpt)
    Set blockStarts = GetBlockStarts(wsRpt)

    For Each bs In blockStarts
        center = Trim$(CStr(wsRpt.Cells(CLng(bs), 2).Value))
        If center = "전  체" Then center = "ALL"

        rowTotal = CLng(bs)
        rowMat = rowTotal + 1
        rowFou = rowTotal + 2
        rowFra = rowTotal + 3
        rowPan = rowTotal + 4
        rowCumTotal = rowTotal + 5
        rowCumMat = rowTotal + 6
        rowCumFou = rowTotal + 7
        rowCumFra = rowTotal + 8
        rowCumPan = rowTotal + 9

        For Each ms In monthStarts
            Set dayCols = GetDayCols(wsRpt, CLng(ms))
            monthTotalCol = GetMonthTotalCol(wsRpt, CLng(ms))
            runTotal = 0: runMat = 0: runFou = 0: runFra = 0: runPan = 0

            For Each dc In dayCols
                d = Trim$(CStr(wsRpt.Cells(4, CLng(dc)).Text))
                arr = GetCounts(dict, d, center)

                vMat = CLng(arr(0))
                vFou = CLng(arr(1))
                vFra = CLng(arr(2))
                vPan = CLng(arr(3))
                vTotal = vMat + vFou + vFra

                runTotal = runTotal + vTotal
                runMat = runMat + vMat
                runFou = runFou + vFou
                runFra = runFra + vFra
                runPan = runPan + vPan

                wsRpt.Cells(rowTotal, CLng(dc)).Value = vTotal
                wsRpt.Cells(rowMat, CLng(dc)).Value = vMat
                wsRpt.Cells(rowFou, CLng(dc)).Value = vFou
                wsRpt.Cells(rowFra, CLng(dc)).Value = vFra
                wsRpt.Cells(rowPan, CLng(dc)).Value = vPan

                wsRpt.Cells(rowCumTotal, CLng(dc)).Value = runTotal
                wsRpt.Cells(rowCumMat, CLng(dc)).Value = runMat
                wsRpt.Cells(rowCumFou, CLng(dc)).Value = runFou
                wsRpt.Cells(rowCumFra, CLng(dc)).Value = runFra
                wsRpt.Cells(rowCumPan, CLng(dc)).Value = runPan
            Next dc

            wsRpt.Cells(rowTotal, monthTotalCol).Value = runTotal
            wsRpt.Cells(rowMat, monthTotalCol).Value = runMat
            wsRpt.Cells(rowFou, monthTotalCol).Value = runFou
            wsRpt.Cells(rowFra, monthTotalCol).Value = runFra
            wsRpt.Cells(rowPan, monthTotalCol).Value = runPan

            wsRpt.Cells(rowCumTotal, monthTotalCol).Value = ""
            wsRpt.Cells(rowCumMat, monthTotalCol).Value = ""
            wsRpt.Cells(rowCumFou, monthTotalCol).Value = ""
            wsRpt.Cells(rowCumFra, monthTotalCol).Value = ""
            wsRpt.Cells(rowCumPan, monthTotalCol).Value = ""

            lastMonthTotalCol = monthTotalCol
        Next ms

        wsRpt.Cells(rowTotal, 227).Value = wsRpt.Cells(rowTotal, lastMonthTotalCol).Value
        wsRpt.Cells(rowMat, 227).Value = wsRpt.Cells(rowMat, lastMonthTotalCol).Value
        wsRpt.Cells(rowFou, 227).Value = wsRpt.Cells(rowFou, lastMonthTotalCol).Value
        wsRpt.Cells(rowFra, 227).Value = wsRpt.Cells(rowFra, lastMonthTotalCol).Value
        wsRpt.Cells(rowPan, 227).Value = wsRpt.Cells(rowPan, lastMonthTotalCol).Value

        If rowTotal = 6 Then
            wsRpt.Cells(rowCumTotal, 227).Value = 1
            overallFinal = CDbl(wsRpt.Cells(rowTotal, 227).Value)
        Else
            If overallFinal > 0 Then
                wsRpt.Cells(rowCumTotal, 227).Value = CDbl(wsRpt.Cells(rowTotal, 227).Value) / overallFinal
            Else
                wsRpt.Cells(rowCumTotal, 227).Value = 0
            End If
        End If

        wsRpt.Cells(rowCumMat, 227).Value = ""
        wsRpt.Cells(rowCumFou, 227).Value = ""
        wsRpt.Cells(rowCumFra, 227).Value = ""
        wsRpt.Cells(rowCumPan, 227).Value = ""
    Next bs

    Application.Calculation = xlCalculationAutomatic
    Application.EnableEvents = True
    Application.ScreenUpdating = True
End Sub

Public Sub ConvertNormalToMacroMode()
    Dim wsRpt As Worksheet
    Set wsRpt = ThisWorkbook.Worksheets("정상")

    Application.ScreenUpdating = False
    Application.EnableEvents = False
    Application.Calculation = xlCalculationManual

    On Error Resume Next
    wsRpt.Range("D6:HS95").SpecialCells(xlCellTypeFormulas).ClearContents
    On Error GoTo 0

    RefreshNormalSheet

    Application.Calculation = xlCalculationAutomatic
    Application.EnableEvents = True
    Application.ScreenUpdating = True
End Sub
