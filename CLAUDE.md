# PDF 자동 편집 (automatic-pdf-editing)

공유폴더에 들어온 PDF + `config.json`을 감시해서 ABBYY 레벨 조정·OCR부터 이미지 재압축·분할·ZIP까지 자동으로 처리하는 프로그램. 자세한 구조와 폴더 규칙은 `README.md`.

## 대상 환경: Windows 전용

- 이 프로젝트는 **Windows 전용**이다. 실제 사용과 모든 테스트는 Windows에서만 한다.
- ABBYY FineReader를 pyautogui로 직접 조작하기 때문에(`pipeline/ocr.py`, `pipeline/abbyy_editor.py`) 다른 환경에서는 애초에 돌지 않는다.
- Mac은 Claude Code에 명령을 내리는 용도일 뿐이다. Mac 환경 문제(GUI, pyautogui, ABBYY 없음 등)는 신경 쓰지 말고, 작업 보고에도 Mac 얘기를 꺼내지 말 것.
- PyMuPDF 계산(합치기·분할·재압축 로직)은 GUI 없이 확인할 수 있지만, 보고할 때는 기계 이름을 적지 않고 "확인한 것"으로만 쓴다.
- 변경 후 보고할 때는 "Windows에서 확인할 항목"만 적는다.

## 실행

```bash
python run_automation.py
```

Windows에서는 `시작.vbs`(창 숨김) 또는 `시작.bat` → `run_automation.py`.

## 파이프라인 순서 (책 1권, `pipeline/runner.py`)

PDF가 여러 개면 각 PDF가 1~2를 따로 거친 뒤 3에서 합쳐진다.

1. **ABBYY** — 레벨 조정 / OCR (스캔타입·OCR 설정에 따라 세 갈래, 300쪽씩 분할해서 처리 후 합침)
2. **이미지 재압축** — 모든 모드. JPEG2000 → JPEG 코덱 변환 (아이패드에서 JPEG2000 디코딩이 무거워 렉이 생기고, NotebookLM은 JPEG2000 PDF를 못 읽음). 이미지 전체를 같은 크기로 다시 인코딩할 뿐 자르지는 않는다
3. **PDF 합치기** — 파일명 숫자 오름차순
4. **분할** (선택) → **출력** → 고객의 모든 책이 끝나면 **ZIP**

여백 자르기 단계(`crop_mm` → `pipeline/crop.py`, CropBox 줄이기)는 없앴다(2026-11-12 사용자 요청). 자르기·기울기 보정 같은 페이지 편집은 `pdf-level-preview`에서 PDF에 직접 넣는다.

## config.json

`pdf-level-preview`의 [설정 저장]이 만드는 파일. `models.py`의 `BookConfig.from_file`이 읽고, 모르는 키는 무시한다(구버전 키도 함께 지원).

| 키 | 내용 |
|---|---|
| `scan_type` | "일반" / "고급" (고급일 때만 레벨 조정) |
| `black_point`, `white_point` | 레벨 값 (ABBYY에 입력) |
| `ocr`, `ocr_language` | OCR 사용 여부, 언어 목록 |
| `is_split`, `split_method`, `split_page_ranges`, `split_size_mb` | 분할 설정 |

옛 config.json에 있는 `crop_mm`(여백 자르기)은 무시한다. `pdf-level-preview`도 더는 쓰지 않는다.

## 주의사항

- ABBYY 완료 판정이 "저장 파일 크기가 안 변하면 끝"이라 페이지가 빠질 수 있다. 조각마다 페이지 수를 검증하고 불일치면 재처리, 끝까지 안 맞으면 출력하지 않고 오류로 마감한다 — 이 안전장치를 없애지 말 것.
- 이미지 재압축은 새 이미지를 추가(`replace_image`)하지 않고 같은 xref를 제자리 교체한다. 추가하면 페이지에 이미지가 중복돼 용량 2배 + 렉이 심해진다.

## 관련 프로젝트

- `/Users/mpc/my-git/pdf-level-preview` — 레벨 값을 눈으로 확인하고 `config.json`을 만드는 GUI 도구. 자르기·기울기 보정·검은 여백 자르기 같은 페이지 편집은 그 도구가 PDF에 직접 넣는다. 이 프로그램의 입력을 만든다.
