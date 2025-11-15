import pandas as pd
import calendar
import numpy as np
import datetime as dt
from dateutil.parser import parse
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ==========================
# 0) 논문 기반 상수 (프로토타입)
# ==========================
# GB/T 13861 코드별 "indicator importance (CRITIC 결과)" — 논문값 활용
CRITIC_WEIGHTS = {
    "120202": 0.14400,   # Illegal operations (H)
    "210103": 0.03800,   # Poor stability (F)
    "43":     0.13900,   # OSH management deficiency (M)
    "210301": 0.00068,   # Naked electrization parts (F)
    "210201": 0.02025,   # Non protected (E)
    "210202": 0.02945,   # Defects of protective devices (E)
    "120201": 0.13300,   # Improper command (H)
    "120203": 0.03236,   # Safety training deficiency (H)
}

HAZARD_NAMES = {
    "120202": "위법 조작",
    "210103": "구조 불안정",
    "43": "안전보건 관리 미흡",
    "210301": "노출 전기부",
    "210201": "미보호 상태",
    "210202": "보호장치 결함",
    "120201": "부적절한 지시",
    "120203": "안전교육 미흡",
}

# 코드 → 카테고리(H/F/E/M) 매핑 (논문 분류 기준)
CODE_CAT = {
    "120202": "H", "120201": "H", "120203": "H",
    "210103": "F", "210301": "F",
    "210201": "E", "210202": "E",
    "43":     "M",
}

# AMI(평균 상호정보량) 기반 조합 위험 (논문 예시값)
AMI_COMBOS = {
    # 2-way
    frozenset(["H","F"]): 0.06531,
    frozenset(["H","E"]): 0.04210,
    frozenset(["H","M"]): 0.05921,
    # 3-way
    frozenset(["H","F","M"]): 0.10774,
    # 4-way
    frozenset(["H","F","E","M"]): 0.16505,
}

# 임계값 (논문에서 제시)
THRESH_R1 = 0.149   # H/F/E 관련 임계
THRESH_R2 = 0.236   # M 관련 임계
MITIGATION_RATE = 0.7  # 점검 완료 시 위험도 감소율

DEFAULT_SITE_NAME = "프로젝트 A 현장"
DEFAULT_SITE_LOCATION = "서울특별시 중구 을지로 100"

if "site_name" not in st.session_state:
    st.session_state["site_name"] = DEFAULT_SITE_NAME
if "site_location" not in st.session_state:
    st.session_state["site_location"] = DEFAULT_SITE_LOCATION
if "user_name" not in st.session_state:
    st.session_state["user_name"] = "홍길동"
if "user_email" not in st.session_state:
    st.session_state["user_email"] = "hong@example.com"
if "user_contact" not in st.session_state:
    st.session_state["user_contact"] = "010-1234-5678"
if "system_notes" not in st.session_state:
    st.session_state["system_notes"] = (
        "1. 좌측에서 공정표와 기상 데이터를 업로드합니다.\n"
        "2. 임계값 파라미터와 현장 정보를 조정합니다.\n"
        "3. 추세/간트/체크리스트 탭에서 위험을 모니터링하고 점검 결과를 기록합니다."
    )

def render_top_info(site_name, site_location, current_dt, weather_items):
    date_str = current_dt.strftime("%Y-%m-%d")
    time_str = current_dt.strftime("%H:%M")
    if weather_items:
        weather_html = "<ul class='weather-list'>" + "".join(weather_items) + "</ul>"
    else:
        weather_html = (
            "<div class='top-info-text'>기상 데이터를 업로드하면 어제·오늘·내일 정보가 표시됩니다.</div>"
        )
    return f"""
    <div class="top-info-card">
      <div class="top-info-grid">
        <div class="top-info-block">
          <div class="top-info-title">현장 명</div>
          <div class="top-info-value">{site_name}</div>
          <div class="top-info-title" style="margin-top: 14px;">현장 위치</div>
          <div class="top-info-text">{site_location}</div>
        </div>
        <div class="top-info-block" style="flex:0 1 220px;">
          <div class="top-info-title">날짜</div>
          <div class="top-info-value">{date_str}</div>
          <div class="top-info-title" style="margin-top: 14px;">시간</div>
          <div class="top-info-text">{time_str}</div>
        </div>
        <div class="top-info-block">
          <div class="top-info-title">날씨</div>
          {weather_html}
        </div>
      </div>
    </div>
    """

CHECKLIST_DATA = [
    {
        "category": "흙막이·굴착부",
        "sections": [
            {
                "subcategory": "흙막이 지보공 설계/시공",
                "items": [
                    {
                        "점검항목": "흙막이 지보공이 설계도서와 동일하게 시공되어 있는가?",
                        "설명": "버팀보 간격·띠장 규격·앵커 배치 등이 설계와 실제 시공이 일치하는지 확인",
                        "점검주기": "착공 시 + 매일",
                        "담당자": "현장소장 / 공사관리자",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "지반 상태",
                "items": [
                    {
                        "점검항목": "굴착면, 기초지반에 침하·균열·용수(물샘) 징후가 없는가?",
                        "설명": "굴착면 및 주변 지반의 균열, 붕괴 흔적, 지하수 유출 여부 확인",
                        "점검주기": "매일 + 강우/해빙 후",
                        "담당자": "시공관리 / 안전관리자",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "버팀보·띠장",
                "items": [
                    {
                        "점검항목": "버팀보·띠장·엄지말뚝에 처짐·변형·이완이 없는가?",
                        "설명": "볼트 풀림, 용접 균열, 휨·좌굴 징후를 육안 및 계측으로 점검",
                        "점검주기": "매일",
                        "담당자": "시공관리 / 안전관리자",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "계측관리",
                "items": [
                    {
                        "점검항목": "계측치(변위·변형률 등)가 관리기준 이내인가?",
                        "설명": "계측값 추세를 확인하고 경보값 초과 시 즉시 공사 중지·보강",
                        "점검주기": "매일(작업 전)",
                        "담당자": "계측 담당 / 현장소장",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "인접 구조물",
                "items": [
                    {
                        "점검항목": "옹벽·건물 등 인접 구조물에 균열·기울어짐이 없는가?",
                        "설명": "기존 구조물 변형 여부, 균열 폭 증가 여부 확인",
                        "점검주기": "주 1회 + 집중호우/해빙 후",
                        "담당자": "시공관리 / 감리",
                        "출처": ""
                    },
                ]
            },
        ],
    },
    {
        "category": "비계·동바리·거푸집",
        "sections": [
            {
                "subcategory": "비계 기초",
                "items": [
                    {
                        "점검항목": "비계 기둥 하부에 깔판·받침판 등 지지기초가 적정한가?",
                        "설명": "지반 침하 방지용 깔판/콘크리트 기초 설치 여부 확인",
                        "점검주기": "설치 시 + 주 1회",
                        "담당자": "시공관리",
                        "출처": "고용노동부"
                    },
                ]
            },
            {
                "subcategory": "비계 구조",
                "items": [
                    {
                        "점검항목": "띠장·가새·벽이음(벽 연결재)가 설계대로 설치되어 있는가?",
                        "설명": "비계 강성을 확보하기 위한 수평·수직 가새, 벽연결 간격 확인",
                        "점검주기": "매일",
                        "담당자": "시공관리 / 안전관리자",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "거푸집 동바리",
                "items": [
                    {
                        "점검항목": "동바리 간격·부재규격·지지방식이 설계기준에 적합한가?",
                        "설명": "동바리 간격, 상하부 결속상태, 상부 지지상태(헤드, 잭서포트 등) 확인",
                        "점검주기": "타설 전 전수",
                        "담당자": "구조/시공관리",
                        "출처": "코딜"
                    },
                ]
            },
            {
                "subcategory": "과적하중",
                "items": [
                    {
                        "점검항목": "슬래브·동바리 위에 자재·장비 과적이 없는가?",
                        "설명": "설계 하중 초과하는 적재 및 중장비 진입 금지 여부 확인",
                        "점검주기": "매일",
                        "담당자": "공사관리 / 안전관리자",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "해체 순서",
                "items": [
                    {
                        "점검항목": "비계·동바리·거푸집 해체가 조립의 역순으로 계획·실행되는가?",
                        "설명": "구조적 안정성을 유지하며 해체하는 절차서 및 TBM 이행 점검",
                        "점검주기": "해체 작업 전·중",
                        "담당자": "공사관리 / 작업반장",
                        "출처": "코딜"
                    },
                ]
            },
        ],
    },
    {
        "category": "구조체·콘크리트",
        "sections": [
            {
                "subcategory": "콘크리트 강도 발현",
                "items": [
                    {
                        "점검항목": "동바리 제거 전 설계강도(또는 해체 허용강도)를 확보했는가?",
                        "설명": "공시체 시험 결과 또는 현장 강도 추정값 확인 후 해체 여부 결정",
                        "점검주기": "동바리 해체 전",
                        "담당자": "품질관리 / 구조기술자",
                        "출처": "이상에듀 +1"
                    },
                ]
            },
            {
                "subcategory": "양생 조건",
                "items": [
                    {
                        "점검항목": "동절기·혹서기 등에서 양생계획에 따른 보온·보습이 이루어졌는가?",
                        "설명": "동절기 보온양생, 여름철 급속 건조 방지 등 구조적 강도 확보 조건 점검",
                        "점검주기": "타설 후 매일",
                        "담당자": "품질관리 / 시공관리",
                        "출처": "이상에듀 +1"
                    },
                ]
            },
            {
                "subcategory": "균열·변형",
                "items": [
                    {
                        "점검항목": "주요 구조부(슬래브, 보, 기둥)에 비정상적인 균열·처짐이 없는가?",
                        "설명": "균열 폭, 처짐량을 기준과 비교하고 이상 시 즉시 원인 분석",
                        "점검주기": "주 1회",
                        "담당자": "구조/시공관리",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "개구부·슬래브 타공",
                "items": [
                    {
                        "점검항목": "설계에 없는 개구부 타공, 슬래브 절단 등 임의 변경은 없는가?",
                        "설명": "구조 안전에 영향 주는 임의 개구부·코어 홀 타공 여부 확인",
                        "점검주기": "공정 전환 시",
                        "담당자": "구조기술자 / 시공관리",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "상부 공정 하중",
                "items": [
                    {
                        "점검항목": "하부 구조체 위 상부 공정 하중(자재 적치, 장비 하중)이 검토되었는가?",
                        "설명": "기존 구조체의 허용하중 범위 내에서 상부 작업 계획 여부 확인",
                        "점검주기": "상부 공정 시작 전",
                        "담당자": "구조기술자 / 공사관리",
                        "출처": ""
                    },
                ]
            },
        ],
    },
    {
        "category": "토공·비탈면·옹벽",
        "sections": [
            {
                "subcategory": "비탈면 안정",
                "items": [
                    {
                        "점검항목": "비탈면에 균열·활동(미끄러짐)·낙석 위험이 없는가?",
                        "설명": "비탈면 상부·사면 중간의 균열, 뜬돌 유무 점검",
                        "점검주기": "주 1회 + 강우 후",
                        "담당자": "토목 담당 / 안전관리자",
                        "출처": "sunsan.co.kr"
                    },
                ]
            },
            {
                "subcategory": "배수 상태",
                "items": [
                    {
                        "점검항목": "사면·옹벽 배수시설(집수정, 배수공)이 막히지 않았는가?",
                        "설명": "우수 배제 불량은 사면·옹벽 붕괴의 주요 원인이므로 배수로 점검",
                        "점검주기": "강우 전/후",
                        "담당자": "토목 담당 / 공사관리",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "옹벽·석축 상태",
                "items": [
                    {
                        "점검항목": "옹벽·석축에 전도·활동 징후 및 블록 파손이 없는가?",
                        "설명": "벽체 기울기, 배부름, 조적 이완, 물흐름 자국 확인",
                        "점검주기": "월 1회 + 호우·해빙기",
                        "담당자": "토목 담당 / 감리",
                        "출처": "kocosa.co.kr +1"
                    },
                ]
            },
            {
                "subcategory": "토류 구조물 변경",
                "items": [
                    {
                        "점검항목": "설계와 다른 굴착 심도·폭 확대 등 무단 변경은 없는가?",
                        "설명": "토류 구조물 검토 범위를 초과하는 변경 여부 확인",
                        "점검주기": "공정 변경 시",
                        "담당자": "설계자 / 시공관리",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "주변 하중",
                "items": [
                    {
                        "점검항목": "사면 상단·옹벽 상부에 중장비·자재 적치 등 집중하중이 없는가?",
                        "설명": "사면 상단의 차량 통행, 자재 적치 금지 구역 설정 여부 확인",
                        "점검주기": "매일",
                        "담당자": "공사관리 / 안전관리자",
                        "출처": ""
                    },
                ]
            },
        ],
    },
    {
        "category": "자재·가설 구조물",
        "sections": [
            {
                "subcategory": "자재 적치 높이",
                "items": [
                    {
                        "점검항목": "철근·폼·블록 등 자재 적치 높이가 기준 이내인가?",
                        "설명": "자재 전도·붕괴 방지를 위한 적치 높이·방식 준수 여부 확인",
                        "점검주기": "매일",
                        "담당자": "공사관리 / 창고관리",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "적치 위치",
                "items": [
                    {
                        "점검항목": "굴착면 상단, 옹벽 상부 등 위험 구역 내 적치가 없는가?",
                        "설명": "붕괴 시 2차 피해 우려 구역에 자재·장비가 없는지 확인",
                        "점검주기": "매일",
                        "담당자": "공사관리",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "가설 컨테이너·창고",
                "items": [
                    {
                        "점검항목": "가설 사무실·휴게실 등의 기초·앵커 고정이 양호한가?",
                        "설명": "기초 침하·앵커 풀림·수평 변형 여부를 점검",
                        "점검주기": "월 1회 + 강풍 후",
                        "담당자": "공사관리 / 안전관리자",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "가설 울타리·펜스",
                "items": [
                    {
                        "점검항목": "가설펜스·방음벽에 전도 위험이 없는가?",
                        "설명": "기초 고정, 지주 간격, 가새 설치 확인",
                        "점검주기": "주 1회 + 강풍 예보 시",
                        "담당자": "공사관리 / 안전관리자",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "데크플레이트·철골 가설지지",
                "items": [
                    {
                        "점검항목": "데크플레이트·철골 부재 가설지지가 설계기준에 맞게 설치되었는가?",
                        "설명": "연결부·용접부·볼트 체결 상태와 지지 간격 확인",
                        "점검주기": "설치 후 + 타설 전",
                        "담당자": "구조/시공관리",
                        "출처": "고용노동부"
                    },
                ]
            },
        ],
    },
    {
        "category": "해체·철거",
        "sections": [
            {
                "subcategory": "해체계획서",
                "items": [
                    {
                        "점검항목": "구조검토를 포함한 해체계획서가 작성·승인되어 있는가?",
                        "설명": "해체 순서, 가설지지, 위험구간 통제 계획 포함 여부 확인",
                        "점검주기": "공사 착수 전",
                        "담당자": "해체 설계자 / 현장소장",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "순차 해체",
                "items": [
                    {
                        "점검항목": "구조안정을 유지할 수 있는 순서로 해체가 이루어지는가?",
                        "설명": "기둥·보·슬래브 등 주요 부재를 동시에 제거하지 않도록 관리",
                        "점검주기": "매 작업일",
                        "담당자": "해체 책임자",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "잔류 구조물 안정성",
                "items": [
                    {
                        "점검항목": "부분 해체 후 남은 구조물의 안정성 검토가 이루어졌는가?",
                        "설명": "보강 여부, 잔류 구조물에 과도한 편심 하중이 없는지 확인",
                        "점검주기": "단계 전환 시",
                        "담당자": "구조기술자 / 해체 책임자",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "인접 시설 보호",
                "items": [
                    {
                        "점검항목": "인접 건물·도로·지하시설 보호를 위한 가시설이 적정한가?",
                        "설명": "비계·보호막·가설 지보공 설치 상태 확인",
                        "점검주기": "공정 변경 시",
                        "담당자": "공사관리 / 해체 책임자",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "폐기물 적치",
                "items": [
                    {
                        "점검항목": "철거 폐기물이 불안정하게 적치되어 붕괴 위험을 유발하지 않는가?",
                        "설명": "폐기물의 분류 적치, 적치 높이, 전도 방지 조치 확인",
                        "점검주기": "매일",
                        "담당자": "해체 책임자 / 공사관리",
                        "출처": ""
                    },
                ]
            },
        ],
    },
    {
        "category": "기상·배수",
        "sections": [
            {
                "subcategory": "기상 특보 대응계획",
                "items": [
                    {
                        "점검항목": "호우·강풍·한파 등 기상특보별 대응계획이 수립되어 있는가?",
                        "설명": "비계·가설구조물 보강, 작업중지 기준 등 포함 여부 확인",
                        "점검주기": "계절 전환기",
                        "담당자": "현장소장 / 안전관리자",
                        "출처": "사단법인 한국사격연맹 +2, 디지털뉴스 +2"
                    },
                ]
            },
            {
                "subcategory": "강우 전 사전점검",
                "items": [
                    {
                        "점검항목": "호우 예보 시 사면·흙막이·배수로 사전점검이 이루어지는가?",
                        "설명": "배수로 청소, 흙막이 지보공 추가 보강 필요성 검토",
                        "점검주기": "호우 예보 시",
                        "담당자": "토목 담당 / 안전관리자",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "해빙기 점검",
                "items": [
                    {
                        "점검항목": "해빙기 지반 연화에 따른 흙막이·비계·동바리 상태를 점검하는가?",
                        "설명": "지반 침하, 기초 지지력 저하로 인한 붕괴 위험 점검",
                        "점검주기": "해빙기 주 1회 이상",
                        "담당자": "현장소장 / 안전관리자",
                        "출처": "사단법인 한국사격연맹 +2, 코샤 +2"
                    },
                ]
            },
            {
                "subcategory": "배수시설 유지관리",
                "items": [
                    {
                        "점검항목": "현장 내 우수 배제 및 집수정, 배수로가 기능을 유지하는가?",
                        "설명": "토사·폐기물로 인한 막힘 여부, 임시 배수로 상태 확인",
                        "점검주기": "주 1회 + 강우 후",
                        "담당자": "공사관리",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "작업중지 기준",
                "items": [
                    {
                        "점검항목": "붕괴 위험 시 작업중지 및 인원 대피 기준이 마련·교육되어 있는가?",
                        "설명": "계측치 초과, 사면 균열 확대, 강풍 속도 등 정량적 기준 설정 여부",
                        "점검주기": "계획 수립 시 + 분기별 재점검",
                        "담당자": "현장소장 / 안전관리자",
                        "출처": ""
                    },
                ]
            },
        ],
    },
    {
        "category": "관리·조직·교육",
        "sections": [
            {
                "subcategory": "붕괴 위험 공정 지정",
                "items": [
                    {
                        "점검항목": "공정표에서 붕괴 고위험 공정(굴착, 타설, 해체 등)이 명확히 태그되어 있는가?",
                        "설명": "시스템 상에서 위험 공정을 구분하여 가중치·알람 연계 가능하도록 설정",
                        "점검주기": "공정표 작성/변경 시",
                        "담당자": "공사관리 / 안전관리자",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "점검 책임자 지정",
                "items": [
                    {
                        "점검항목": "각 붕괴 위험 항목별 책임자와 대리자가 지정되어 있는가?",
                        "설명": "붕괴 관련 체크리스트의 “담당자”가 실명으로 기입되어 있는지 확인",
                        "점검주기": "착공 시 + 인사 변경 시",
                        "담당자": "현장소장",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "교육·TBM",
                "items": [
                    {
                        "점검항목": "붕괴 위험 공정 착수 전 TBM(작업 전 회의)에서 해당 위험요인을 교육하는가?",
                        "설명": "점검항목·작업중지 기준·비상연락망 전달 여부 확인",
                        "점검주기": "공정 전",
                        "담당자": "안전관리자 / 작업반장",
                        "출처": "고용노동부 +1"
                    },
                ]
            },
            {
                "subcategory": "이력 관리",
                "items": [
                    {
                        "점검항목": "붕괴 관련 점검결과·조치사항이 시스템에 누적 기록되는가?",
                        "설명": "일일점검 결과, 사진, 보강조치 이력을 시스템에 저장해 경향 분석 가능하도록 함",
                        "점검주기": "상시",
                        "담당자": "안전관리자 / 공사관리",
                        "출처": ""
                    },
                ]
            },
            {
                "subcategory": "외부 점검·감리",
                "items": [
                    {
                        "점검항목": "법정 점검·감리 지적사항 중 붕괴 위험 관련 사항이 즉시 조치되는가?",
                        "설명": "감리·관계기관 지적사항의 조치 완료 여부를 추적 관리",
                        "점검주기": "점검 후 즉시 + 월 1회 검토",
                        "담당자": "현장소장 / 안전관리자",
                        "출처": ""
                    },
                ]
            },
        ],
    },
]

# ==========================
# 1) UI (레이아웃/스타일)
# ==========================
st.set_page_config(page_title="시간누적 × 공정기반 붕괴위험 대시보드", layout="wide", initial_sidebar_state="expanded")
st.markdown(
    """
    <style>
      [data-testid="stAppViewContainer"] > .main {
        background: linear-gradient(180deg, #f3f6fc 0%, #ffffff 45%);
      }
      .block-container {
        padding-top: 1.4rem;
        padding-bottom: 2rem;
        max-width: min(92vw, 1400px);
      }
      .top-info-card {
        background: #ffffff;
        border-radius: 22px;
        padding: 26px 28px;
        margin-top: 12px;
        margin-bottom: 26px;
        box-shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
      }
      .top-info-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 32px;
      }
      .top-info-block {
        flex: 1 1 280px;
        min-width: 220px;
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .top-info-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
      .top-info-value {
        font-size: 1.35rem;
        font-weight: 700;
        color: #0f172a;
      }
      .top-info-text {
        font-size: 0.98rem;
        color: #1f2937;
        line-height: 1.5;
      }
      .weather-list {
        list-style: none;
        padding: 0;
        margin: 0;
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .weather-list li {
        font-size: 0.95rem;
        color: #1f2937;
      }
      .section-title {
        font-size: 1.35rem;
        font-weight: 700;
        color: #0f172a;
        margin: 10px 0 18px;
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .section-title::after {
        content: "";
        flex: 1;
        height: 1px;
        background: linear-gradient(90deg, rgba(59,130,246,0.35), rgba(59,130,246,0));
      }
      .metric-grid {
        display: flex;
        gap: 26px;
        width: 100%;
        margin-bottom: 6px;
        flex-wrap: wrap;
      }
      .metric-card {
        background: #ffffff;
        border-radius: 18px;
        padding: 20px 22px;
        box-shadow: 0 15px 36px rgba(15, 23, 42, 0.08);
        margin-bottom: 12px;
        min-height: 148px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 12px;
        white-space: nowrap;
        overflow: hidden;
      }
      .metric-card.metric-span-2 {
        flex: 2.2;
      }
      .metric-card.metric-span-1 {
        flex: 1;
      }
      .metric-card .metric-label {
        font-size: 0.85rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }
      .metric-card .metric-value {
        margin-top: 2px;
        font-size: 1.8rem;
        font-weight: 700;
        color: #0f172a;
        text-overflow: ellipsis;
        overflow: hidden;
      }
      .metric-card .metric-value span.highlight {
        color: #e11d48;
      }
      .metric-card .metric-value-inline {
        display: inline-block;
      }
      .summary-alert-card {
        background: linear-gradient(120deg, #fff2f1 0%, #ffe3e3 100%);
        border-radius: 18px;
        padding: 18px 24px;
        margin-top: 18px;
        margin-bottom: 18px;
        box-shadow: 0 16px 32px rgba(239, 68, 68, 0.18);
        color: #b91c1c;
      }
      .summary-info-card {
        background: #f4f8ff;
        border-radius: 18px;
        padding: 16px 24px;
        margin-top: 14px;
        margin-bottom: 14px;
        box-shadow: 0 14px 30px rgba(59, 130, 246, 0.14);
        color: #1d4ed8;
      }
      .summary-alert-card p,
      .summary-info-card p {
        margin: 0 0 6px 0;
        font-size: 0.98rem;
      }
    </style>
    """,
    unsafe_allow_html=True
)

col_title, col_help = st.columns([0.85, 0.15])
with col_title:
    st.title("시간누적 × 공정기반 붕괴위험 대시보드 (Prototype)")
with col_help:
    st.caption("좌측 사이드바에서 **파라미터/임계값**을 조정해 시나리오를 확인하세요.")

site_name_value = st.session_state.get("site_name", DEFAULT_SITE_NAME)
site_location_value = st.session_state.get("site_location", DEFAULT_SITE_LOCATION)
current_datetime = dt.datetime.now()
info_placeholder = st.empty()
info_placeholder.markdown(
    render_top_info(site_name_value, site_location_value, current_datetime, []),
    unsafe_allow_html=True
)

with st.sidebar:
    st.header("데이터 업로드")
    st.text_input("현장 명", key="site_name")
    st.text_input("현장 위치", key="site_location")
    sch_file = st.file_uploader("공정표 엑셀", type=["xlsx"], help="열 이름: task_id, task_name, zone, planned_start, planned_end, actual_end, hazard_codes")
    wea_file = st.file_uploader("기상 엑셀", type=["xlsx"], help="열 이름: date, address, daily_rain_mm, max_wind_ms, avg_temp_C")
    mapping_file = st.file_uploader("위험요인 매핑 엑셀 (선택)", type=["xlsx"], help="열 이름: task_type, hazard_codes")
    st.caption("샘플 파일은 본문 상단 설명의 링크에서 내려받으세요.")

    st.markdown("---")
    st.subheader("설정")
    tab_account, tab_profile, tab_manual = st.tabs(["내 계정", "내 정보", "시스템 설명"])

    with tab_account:
        st.session_state["user_name"] = st.text_input("이름", value=st.session_state["user_name"])
        st.session_state["user_email"] = st.text_input("이메일", value=st.session_state["user_email"])
    with tab_profile:
        st.session_state["user_contact"] = st.text_input("연락처", value=st.session_state["user_contact"])
        st.text_area("비고", value=st.session_state.get("user_profile_notes", ""), key="user_profile_notes", height=80)
    with tab_manual:
        st.session_state["system_notes"] = st.text_area(
            "사용 설명",
            value=st.session_state["system_notes"],
            height=160
        )

    with st.expander("시간누적 I 파라미터", expanded=True):
        mu_days  = st.number_input("평균 시정시간 μ (일)", min_value=0.0, value=1.0, step=0.5)
        xi_days  = st.number_input("최대 허용 시정시간 ξ (일)", min_value=0.1, value=5.0, step=0.5)
        k_repeat = st.number_input("반복 발생 지수 k", min_value=1.0, value=1.0, step=1.0)
        st.markdown(
            """
            <small>
            • **평균 시정시간 μ**: 공정 지연이 발생했을 때 통상적으로 허용되는 평균 조치 시간입니다.<br>
            • **최대 허용 시정시간 ξ**: μ를 넘는 지연이 지속될 경우 위험도가 급격히 상승하는 상한선입니다.<br>
            • **반복 발생 지수 k**: 같은 유형의 지연이 반복될 때 위험도를 얼마나 가중할지 결정하는 지수입니다.
            </small>
            """,
            unsafe_allow_html=True,
        )

    with st.expander("기상 상태 임계값", expanded=True):
        rain_thr = st.number_input("일 강수량 ≥ (mm)", min_value=0.0, value=10.0, step=1.0)
        wind_thr = st.number_input("최대 풍속 ≥ (m/s)", min_value=0.0, value=10.0, step=1.0)

st.markdown("---")

# ==========================
# 2) 함수 (계산 로직)
# ==========================
def to_date(x):
    if pd.isna(x):
        return None
    if isinstance(x, (dt.date, dt.datetime, pd.Timestamp)):
        return pd.to_datetime(x).date()
    return parse(str(x)).date()

def parse_codes(cell):
    if pd.isna(cell):
        return []
    return [c.strip() for c in str(cell).split(",") if c.strip()]

def active_tasks_on_date(df, day):
    # day: date
    mask = (df["planned_start"] <= day) & (df["planned_end"] >= day)
    return df[mask].copy()

def compute_I_for_task(day, row, mu, xi, k):
    """
    시간누적 증가항 I 구성요소: 각 코드별 a_i0 * ((|x-μ|)/(ξ-μ))^k
    여기서 x = (지연일수) = max(0, min(day, actual_end) - planned_end)
    """
    planned_end = row["planned_end"]
    actual_end  = row["actual_end"]
    if actual_end is None or planned_end is None:
        return 0.0

    x_days = 0
    if day > planned_end:
        end_cap = min(day, actual_end) if actual_end else day
        if end_cap > planned_end:
            x_days = (end_cap - planned_end).days

    if x_days <= mu:
        return 0.0

    denom = max(xi - mu, 1e-6)
    factor = ((abs(x_days - mu)) / denom) ** k

    hazard_codes = row["hazard_codes"]
    I_val = 0.0
    for code in hazard_codes:
        a_i0 = CRITIC_WEIGHTS.get(code, 0.0)
        I_val += a_i0 * factor
    return I_val

def categories_present(codes, env_flag=False):
    cats = set()
    for c in codes:
        cat = CODE_CAT.get(c)
        if cat:
            cats.add(cat)
    # 환경 트리거(강풍/강우 등)로 E 강제 활성화
    if env_flag:
        cats.add("E")
    return cats

def choose_RC(cats):
    """
    AMI 조합 중 적용 가능한 것들 중 '최대값' 하나만 사용 (과다중복 방지 목적의 프로토타입 규칙)
    """
    if not cats:
        return 0.0
    best = 0.0
    for combo, val in AMI_COMBOS.items():
        if combo.issubset(cats):
            best = max(best, val)
    return best

def risk_level(R1, R2):
    if R1 >= THRESH_R1:
        return "Level I (Red)"
    elif R2 >= THRESH_R2:
        return "Level II (Yellow)"
    else:
        return "Level III (Blue)"

def build_weather_summary(wea_df, ref_date=None):
    if wea_df is None or wea_df.empty:
        return []
    if ref_date is None:
        ref_date = dt.date.today()
    labels = [
        ("어제", ref_date - dt.timedelta(days=1)),
        ("오늘", ref_date),
        ("내일", ref_date + dt.timedelta(days=1)),
    ]
    summary = []
    for label, day in labels:
        row = wea_df[wea_df["date"] == day]
        if row.empty:
            summary.append(f"<li><strong>{label} ({day:%m-%d})</strong> · 데이터 없음</li>")
        else:
            rain = float(row["daily_rain_mm"].iloc[0]) if "daily_rain_mm" in row else 0.0
            wind = float(row["max_wind_ms"].iloc[0]) if "max_wind_ms" in row else 0.0
            temp = row["avg_temp_C"].iloc[0] if "avg_temp_C" in row else None
            temp_txt = f"{float(temp):.1f}℃" if temp is not None and not pd.isna(temp) else "정보 없음"
            summary.append(
                f"<li><strong>{label} ({day:%m-%d})</strong> · 강수 {rain:.1f}mm · 풍속 {wind:.1f}m/s · 평균기온 {temp_txt}</li>"
            )
    return summary

def build_threshold_alerts(df):
    """
    입력된 일자별 위험도 데이터프레임에서 임계값(R1, R2) 초과 일자를 추출한다.
    """
    alerts = []
    for _, row in df.iterrows():
        reasons = []
        if row["R1(H/F/E)"] >= THRESH_R1:
            reasons.append(f"R1 ≥ {THRESH_R1:.3f}")
        if row["R2(M)"] >= THRESH_R2:
            reasons.append(f"R2 ≥ {THRESH_R2:.3f}")
        if reasons:
            alerts.append({
                "점검일시": row["date"],
                "위험레벨": row["level"],
                "초과지표": ", ".join(reasons),
                "R_total": row["R_total"],
                "R1(H/F/E)": row["R1(H/F/E)"],
                "R2(M)": row["R2(M)"],
            })
    if not alerts:
        return pd.DataFrame(columns=["점검일시", "위험레벨", "초과지표", "R_total", "R1(H/F/E)", "R2(M)"])
    return pd.DataFrame(alerts).sort_values("점검일시")

def apply_mitigation(df, checks, rate=MITIGATION_RATE):
    """
    점검 완료된 일자에 대해 위험도를 감소시킨다.
    rate: 0~1 사이 감소율 (0.7이면 70% 감소 → 잔여 30%)
    """
    if not checks:
        return df
    df = df.copy()
    reduction_factor = max(0.0, min(1.0, 1 - rate))
    if reduction_factor == 1.0:
        return df
    cols = ["R_total", "R1(H/F/E)", "R2(M)"]
    for date_key, done in checks.items():
        if not done:
            continue
        try:
            date_obj = pd.to_datetime(str(date_key)).date()
        except Exception:
            continue
        mask = df["date"] == date_obj
        if not mask.any():
            continue
        df.loc[mask, cols] = (df.loc[mask, cols] * reduction_factor).clip(lower=0)
        df.loc[mask, "level"] = df.loc[mask].apply(
            lambda row: risk_level(row["R1(H/F/E)"], row["R2(M)"]),
            axis=1
        )
    return df

def prepare_alert_table(base_alerts, adjusted_daily, checks):
    """
    임계 초과 알림 표를 생성한다.
    base_alerts : 점검 전(원본) 위험도 기반 알림
    adjusted_daily : 조정(감소) 적용 후 일자별 위험도
    checks : session_state에 저장된 점검 완료 여부
    """
    columns = [
        "번호", "점검완료", "점검일시", "초과지표",
        "기준 위험레벨", "현재 위험레벨",
        "기준 R_total", "현재 R_total",
        "기준 R1(H/F/E)", "현재 R1(H/F/E)",
        "기준 R2(M)", "현재 R2(M)",
    ]
    if base_alerts.empty:
        return pd.DataFrame(columns=columns)

    table = base_alerts.rename(columns={
        "위험레벨": "기준 위험레벨",
        "R_total": "기준 R_total",
        "R1(H/F/E)": "기준 R1(H/F/E)",
        "R2(M)": "기준 R2(M)",
    }).copy()

    table = table.merge(
        adjusted_daily[["date", "R_total", "R1(H/F/E)", "R2(M)", "level"]],
        left_on="점검일시",
        right_on="date",
        how="left"
    )
    table.rename(columns={
        "R_total": "현재 R_total",
        "R1(H/F/E)": "현재 R1(H/F/E)",
        "R2(M)": "현재 R2(M)",
        "level": "현재 위험레벨",
    }, inplace=True)
    table.drop(columns=["date"], inplace=True)

    table = table.sort_values("점검일시").reset_index(drop=True)
    table.insert(0, "번호", np.arange(1, len(table) + 1))

    def _checked_flag(date_val):
        if pd.isna(date_val):
            return False
        if isinstance(date_val, dt.date):
            key = date_val.isoformat()
        else:
            key = pd.to_datetime(date_val).date().isoformat()
        return bool(checks.get(key, False))

    table.insert(1, "점검완료", table["점검일시"].apply(_checked_flag))

    float_cols = [
        "기준 R_total", "현재 R_total",
        "기준 R1(H/F/E)", "현재 R1(H/F/E)",
        "기준 R2(M)", "현재 R2(M)",
    ]
    for col in float_cols:
        if col in table.columns:
            table[col] = table[col].astype(float).round(3)

    return table[columns]

# ==========================
# 3) 데이터 로딩
# ==========================
if sch_file is not None and wea_file is not None:
    sch = pd.read_excel(sch_file)
    wea = pd.read_excel(wea_file)

    # 위험요인 매핑 엑셀 로드 (선택)
    mapping_df = None
    if "mapping_file" in globals() and mapping_file is not None:
        try:
            mapping_df = pd.read_excel(mapping_file)
        except Exception:
            mapping_df = None

    # 표준화
    sch = sch.rename(columns={
        "task_id":"task_id",
        "task_name":"task_name",
        "zone":"zone",
        "planned_start":"planned_start",
        "planned_end":"planned_end",
        "actual_end":"actual_end",
        "hazard_codes":"hazard_codes"
    })
    # hazard_codes 컬럼이 없으면 생성
    if "hazard_codes" not in sch.columns:
        sch["hazard_codes"] = np.nan

    # 별도 매핑 엑셀을 통한 hazard_codes 자동 부여
    if mapping_df is not None and "task_type" in sch.columns:
        if "task_type" in mapping_df.columns and "hazard_codes" in mapping_df.columns:
            # 문자열로 정규화
            sch["task_type"] = sch["task_type"].astype(str)
            mapping_df_local = mapping_df[["task_type", "hazard_codes"]].copy()
            mapping_df_local["task_type"] = mapping_df_local["task_type"].astype(str)
            mapping_df_local["hazard_codes"] = mapping_df_local["hazard_codes"].astype(str)
            # task_type 기준 병합
            sch = sch.merge(mapping_df_local, on="task_type", how="left", suffixes=("", "_map"))
            # 사용자가 공정표에 hazard_codes를 비워둔 경우에만 매핑값 채우기
            def _fill_hazard_codes(row):
                val = row.get("hazard_codes")
                if val is None or (isinstance(val, float) and np.isnan(val)) or str(val).strip() == "":
                    return row.get("hazard_codes_map")
                return val
            sch["hazard_codes"] = sch.apply(_fill_hazard_codes, axis=1)
            if "hazard_codes_map" in sch.columns:
                sch.drop(columns=["hazard_codes_map"], inplace=True)

    # 날짜 변환
    for col in ["planned_start","planned_end","actual_end"]:
        sch[col] = sch[col].apply(to_date)
    # 코드 리스트 변환
    sch["hazard_codes"] = sch["hazard_codes"].apply(parse_codes)

    wea = wea.rename(columns={
        "date":"date","address":"address",
        "daily_rain_mm":"daily_rain_mm",
        "max_wind_ms":"max_wind_ms",
        "avg_temp_C":"avg_temp_C"
    })
    wea["date"] = wea["date"].apply(to_date)

    weather_lines = build_weather_summary(wea, ref_date=current_datetime.date())
    info_placeholder.markdown(
        render_top_info(
            st.session_state.get("site_name", DEFAULT_SITE_NAME),
            st.session_state.get("site_location", DEFAULT_SITE_LOCATION),
            current_datetime,
            weather_lines
        ),
        unsafe_allow_html=True
    )

    date_min = min(sch["planned_start"].min(), wea["date"].min())
    date_max = max(sch["planned_end"].max(), wea["date"].max())
    all_days = pd.date_range(start=date_min, end=date_max, freq="D").date

    # ==========================
    # 4) 계산 루프
    # ==========================
    daily_rows = []
    per_task_rows = []

    for day in all_days:
        # 오늘 날씨
        wrow = wea[wea["date"]==day]
        rain = float(wrow["daily_rain_mm"].iloc[0]) if not wrow.empty else 0.0
        wind = float(wrow["max_wind_ms"].iloc[0])   if not wrow.empty else 0.0

        # 환경 트리거 플래그
        env_trigger = (rain >= rain_thr) or (wind >= wind_thr)

        # 오늘 활성 태스크
        act = active_tasks_on_date(sch, day)

        # 베이스 위험 (ΣRi0), 시간누적 I, 조합 RC 를 누적
        sum_Ri0_all = 0.0
        sum_I_all   = 0.0
        sum_Ri0_HFE = 0.0  # R1 계산용(H/F/E만)
        sum_Ri0_M   = 0.0  # R2 계산용(관리)

        day_codes = []  # 전체 조합 판단용

        for _, row in act.iterrows():
            codes = row["hazard_codes"]
            # 베이스 위험 합
            Ri0 = sum(CRITIC_WEIGHTS.get(c, 0.0) for c in codes)
            sum_Ri0_all += Ri0

            # 카테고리 분해
            for c in codes:
                cat = CODE_CAT.get(c)
                val = CRITIC_WEIGHTS.get(c, 0.0)
                if cat in ["H","F","E"]:
                    sum_Ri0_HFE += val
                elif cat == "M":
                    sum_Ri0_M   += val

            # 시간누적 I
            I_val = compute_I_for_task(day, row, mu_days, xi_days, k_repeat)
            sum_I_all += I_val

            # 일자-태스크별 결과 저장 (상세뷰)
            per_task_rows.append({
                "date": day,
                "task_id": row["task_id"],
                "task_name": row["task_name"],
                "zone": row.get("zone",""),
                "Ri0_sum": Ri0,
                "I": I_val
            })

            day_codes.extend(codes)

        # 카테고리 세트 (환경 트리거 반영)
        cats = categories_present(day_codes, env_flag=env_trigger)
        RC = choose_RC(cats)

        # 최종 위험
        R_total = sum_Ri0_all + sum_I_all + RC
        R1 = sum_Ri0_HFE + sum_I_all + (choose_RC(cats & set(["H","F","E"])) if cats else 0.0)
        R2 = sum_Ri0_M

        lvl = risk_level(R1, R2)

        daily_rows.append({
            "date": day,
            "R_total": R_total,
            "R1(H/F/E)": R1,
            "R2(M)": R2,
            "RC(AMI)": RC,
            "I(delay)": sum_I_all,
            "rain_mm": rain,
            "wind_ms": wind,
            "level": lvl
        })

    daily_df = pd.DataFrame(daily_rows)
    per_task_df = pd.DataFrame(per_task_rows)

    daily_df_base = daily_df.copy()
    alert_checks_state = st.session_state.setdefault("alert_checks", {})
    daily_df = apply_mitigation(daily_df, alert_checks_state)

    # ---------- UI 전용 뷰 필터(계산 결과 변경 없음) ----------
    st.markdown("<div class='section-title'>요약</div>", unsafe_allow_html=True)
    summary_cards = [
        ("기간", f"<span class='metric-value-inline'>{daily_df['date'].min()} ~ {daily_df['date'].max()}</span>", "metric-card metric-span-2"),
        ("평균 R_total", f"{daily_df['R_total'].mean():.3f}", "metric-card metric-span-1"),
        ("최대 R1(H/F/E)", f"{daily_df['R1(H/F/E)'].max():.3f}", "metric-card metric-span-1"),
        ("Level I(빨강) 일수", f"<span class='highlight'>{int((daily_df['level'] == 'Level I (Red)').sum())}</span>", "metric-card metric-span-1"),
    ]
    summary_html = "<div class='metric-grid'>" + "".join(
        f"<div class='{classes}'><div class='metric-label'>{label}</div>"
        f"<div class='metric-value'>{value_html}</div></div>"
        for label, value_html, classes in summary_cards
    ) + "</div>"
    st.markdown(summary_html, unsafe_allow_html=True)

    today = dt.date.today()
    highlight_messages = []

    if not daily_df.empty:
        today_row = daily_df[daily_df["date"] == today]
        today_row_base = daily_df_base[daily_df_base["date"] == today]

        if not today_row.empty:
            level_text = today_row["level"].iloc[0]
            level_dict = {
                "Level I (Red)": "Level I (Red) (즉시 대응 필요)",
                "Level II (Yellow)": "Level II (Yellow)",
                "Level III (Blue)": "Level III (Blue)",
            }
            highlight_messages.append(
                f"<strong>오늘 {today:%Y-%m-%d}</strong>은 {level_dict.get(level_text, level_text)} 상태입니다."
            )

            base_need = False
            if not today_row_base.empty:
                base_need = (
                    today_row_base["R1(H/F/E)"].iloc[0] >= THRESH_R1 or
                    today_row_base["R2(M)"].iloc[0] >= THRESH_R2
                )
            check_key = today.isoformat()
            checked_today = alert_checks_state.get(check_key, False)

            if base_need and not checked_today:
                highlight_messages.append("<strong>오늘</strong>은 임계 초과로 점검이 필요한 날입니다.")
            elif base_need and checked_today:
                highlight_messages.append("<strong>오늘</strong> 점검을 완료하여 위험도가 감소한 상태입니다.")
        else:
            if today < daily_df['date'].min() or today > daily_df['date'].max():
                highlight_messages.append(f"<strong>오늘 {today:%Y-%m-%d}</strong>은 업로드된 데이터 기간 밖입니다.")
            else:
                highlight_messages.append(f"<strong>오늘 {today:%Y-%m-%d}</strong> 데이터가 누락되었습니다. 입력을 확인하세요.")

    if "sch" in locals() and not sch.empty:
        today_tasks = sch[
            sch["planned_start"].notna()
            & sch["planned_end"].notna()
            & (sch["planned_start"] <= today)
            & (sch["planned_end"] >= today)
        ]
        if not today_tasks.empty:
            task_names = today_tasks["task_name"].dropna().astype(str).tolist()
            if task_names:
                display_names = ", ".join(task_names[:3])
                if len(task_names) > 3:
                    display_names += f" 외 {len(task_names) - 3}개 공정"
                highlight_messages.append(f"<strong>오늘 진행 중 공정</strong>: {display_names}")
        else:
            highlight_messages.append("<strong>오늘</strong>은 진행 중인 공정이 없습니다.")

    highlight_alerts = []
    for msg in highlight_messages:
        css_class = "summary-info-card"
        if any(keyword in msg for keyword in ["Level I", "임계 초과", "즉시 대응", "누락", "기간 밖"]):
            css_class = "summary-alert-card"
        highlight_alerts.append((css_class, msg))

    for css_class, msg in highlight_alerts:
        st.markdown(f"<div class='{css_class}'><p>{msg}</p></div>", unsafe_allow_html=True)

    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

    # 날짜 범위 필터(표시용)
    st.markdown("#### 표시 범위 선택")
    fcol1, fcol2 = st.columns([1,3])
    with fcol1:
        view_range = st.date_input(
            "표시 기간",
            value=(daily_df["date"].min(), daily_df["date"].max()),
            min_value=daily_df["date"].min(),
            max_value=daily_df["date"].max()
        )
    if isinstance(view_range, tuple):
        vmin, vmax = view_range
    else:
        vmin, vmax = daily_df["date"].min(), daily_df["date"].max()
    view_daily_base = daily_df_base[(daily_df_base["date"]>=vmin) & (daily_df_base["date"]<=vmax)].copy()
    view_daily = daily_df[(daily_df["date"]>=vmin) & (daily_df["date"]<=vmax)].copy()
    view_tasks = per_task_df[(per_task_df["date"]>=vmin) & (per_task_df["date"]<=vmax)].copy()
    view_alerts_base = build_threshold_alerts(view_daily_base)
    view_alerts_active = build_threshold_alerts(view_daily)
    alerts_table_display = prepare_alert_table(view_alerts_base, view_daily, alert_checks_state)
    total_alert_count = len(view_alerts_base)
    remaining_alert_count = len(view_alerts_active)

    # 색상 매핑(시각 일관성)
    level_color_map = {
        "Level I (Red)":    "#B10000",
        "Level II (Yellow)":"#FFB000",
        "Level III (Blue)": "#1F6FEB",
    }

    tabs = st.tabs(["📅 달력 뷰", "📈 추세", "🧱 공정 Gantt", "📊 위험요인/조합", "🌦️ 기상-위험 상관", "🔎 데이터", "✅ 체크리스트"])

    # ==========================
    # 5) 시각화
    # ==========================
    with tabs[0]:
        st.subheader("① 달력 뷰 (월별 격자)")

        mcol1, mcol2, mcol3 = st.columns([1.2, 1, 1])
        with mcol1:
            metric = st.radio(
                "표시 지표",
                options=["R_total","R1(H/F/E)","R2(M)"],
                horizontal=True
            )

        ym_list = (
            view_daily.assign(year=pd.to_datetime(view_daily["date"]).dt.year,
                              month=pd.to_datetime(view_daily["date"]).dt.month)
            [["year","month"]].drop_duplicates().sort_values(["year","month"]).values.tolist()
        )
        if not ym_list:
            st.info("표시구간 내 데이터가 없습니다.")
        else:
            y_default, m_default = ym_list[0]
            with mcol2:
                year = st.selectbox("연도", sorted({y for y, _ in ym_list}),
                                    index=sorted({y for y, _ in ym_list}).index(y_default))
            with mcol3:
                month_choices = [m for (y, m) in ym_list if y == year]
                month = st.selectbox("월", month_choices, index=0)

            cal = calendar.Calendar(firstweekday=6)  # 6=Sunday
            weeks = cal.monthdatescalendar(year, month)

            val_by_date = dict(zip(view_daily["date"], view_daily[metric]))

            z, texts, hovertexts = [], [], []
            month_mask = (view_daily["date"] >= dt.date(year, month, 1)) & \
                         (view_daily["date"] <= dt.date(year, month, calendar.monthrange(year, month)[1]))
            month_vals = view_daily.loc[month_mask, metric]
            zmin = float(month_vals.min()) if len(month_vals) else 0.0
            zmax = float(month_vals.max()) if len(month_vals) else 1.0
            if zmin == zmax:
                zmax = zmin + 1e-6

            for w in weeks:
                z_row, text_row, hover_row = [], [], []
                for d in w:
                    if d.month != month:
                        z_row.append(None)
                        text_row.append("")
                        hover_row.append("")
                    else:
                        v = val_by_date.get(d, None)
                        z_row.append(v if v is not None else None)
                        text_row.append(str(d.day))

                        drow = view_daily[view_daily["date"] == d]
                        if not drow.empty:
                            rtot = drow["R_total"].iloc[0]
                            r1   = drow["R1(H/F/E)"].iloc[0]
                            r2   = drow["R2(M)"].iloc[0]
                            rc   = drow["RC(AMI)"].iloc[0]
                            ide  = drow["I(delay)"].iloc[0]
                            rain = drow["rain_mm"].iloc[0]
                            wind = drow["wind_ms"].iloc[0]
                            lvl  = drow["level"].iloc[0]
                            hover_row.append(
                                f"{d:%Y-%m-%d}<br>"
                                f"Level: {lvl}<br>"
                                f"R_total: {rtot:.3f}<br>"
                                f"R1(H/F/E): {r1:.3f} · R2(M): {r2:.3f}<br>"
                                f"RC(AMI): {rc:.3f} · I(delay): {ide:.3f}<br>"
                                f"Rain: {rain:.1f} mm · Wind: {wind:.1f} m/s"
                            )
                        else:
                            hover_row.append(f"{d:%Y-%m-%d}<br>데이터 없음")
                z.append(z_row); texts.append(text_row); hovertexts.append(hover_row)

            x_labels = ["S","M","T","W","Th","F","Sa"]
            y_labels = [f"W{idx+1}" for idx in range(len(weeks))]

            colorscale = [
                [0.00, "#E6F4EA"],
                [0.25, "#CDEAC0"],
                [0.50, "#F6E58D"],
                [0.75, "#F5A623"],
                [1.00, "#B10000"],
            ]

            fig_grid = go.Figure(
                data=go.Heatmap(
                    z=z, x=x_labels, y=y_labels,
                    text=texts, texttemplate="%{text}",
                    hovertext=hovertexts, hoverinfo="text",
                    colorscale=colorscale, zmin=zmin, zmax=zmax,
                    xgap=2, ygap=2,
                    colorbar=dict(title=metric, thickness=10, len=0.7)
                )
            )
            fig_grid.update_layout(
                height=420,
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(
                    side="top",
                    showgrid=False, showline=False, zeroline=False,
                    ticks="", showticklabels=True
                ),
                yaxis=dict(
                    autorange="reversed",
                    showgrid=False, showline=False, zeroline=False,
                    ticks="", showticklabels=False
                ),
                title=None,
            )
            st.plotly_chart(fig_grid, use_container_width=True)

    with tabs[1]:
        st.subheader("② 일자별 추세 (R_total / R1 / R2)")

        lcol1, lcol2, lcol3 = st.columns([1.2, 1, 1])
        with lcol1:
            smooth = st.toggle("스무딩 곡선 적용", value=True)
        with lcol2:
            show_marker = st.toggle("마커 표시", value=False)
        with lcol3:
            scale_mode = st.radio(
                "Y축 범위",
                ["자동", "0 기준 고정"],
                horizontal=True,
                label_visibility="collapsed"
            )

        line_df = view_daily.melt(
            id_vars=["date"],
            value_vars=["R_total","R1(H/F/E)","R2(M)"],
            var_name="metric",
            value_name="value"
        )

        color_map = {"R_total": "#B10000", "R1(H/F/E)": "#F5A623", "R2(M)": "#1F6FEB"}
        dash_map  = {"R_total": "solid", "R1(H/F/E)": "dot", "R2(M)": "dash"}

        fig_line = go.Figure()
        for metric in ["R_total","R1(H/F/E)","R2(M)"]:
            df_m = line_df[line_df["metric"] == metric]
            fig_line.add_trace(
                go.Scatter(
                    x=df_m["date"], y=df_m["value"],
                    mode="lines+markers" if show_marker else "lines",
                    name=metric,
                    line=dict(
                        color=color_map[metric],
                        width=3,
                        dash=dash_map[metric],
                        shape="spline" if smooth else "linear",
                    ),
                    marker=dict(size=6, opacity=0.7),
                    hovertemplate="<b>%{x|%Y-%m-%d}</b><br>%{y:.3f}<extra>"+metric+"</extra>",
                )
            )

        exceed_r1 = view_daily[view_daily["R1(H/F/E)"] >= THRESH_R1]
        if not exceed_r1.empty:
            fig_line.add_trace(
                go.Scatter(
                    x=exceed_r1["date"],
                    y=exceed_r1["R1(H/F/E)"],
                    mode="markers",
                    name="R1 임계 초과",
                    marker=dict(
                        size=10,
                        symbol="diamond",
                        color=color_map["R1(H/F/E)"],
                        line=dict(width=1, color="#000000"),
                    ),
                    hovertemplate="<b>%{x|%Y-%m-%d}</b><br>R1 %{y:.3f}<extra>R1 임계 초과</extra>",
                    showlegend=True,
                )
            )

        exceed_r2 = view_daily[view_daily["R2(M)"] >= THRESH_R2]
        if not exceed_r2.empty:
            fig_line.add_trace(
                go.Scatter(
                    x=exceed_r2["date"],
                    y=exceed_r2["R2(M)"],
                    mode="markers",
                    name="R2 임계 초과",
                    marker=dict(
                        size=10,
                        symbol="diamond-open",
                        color=color_map["R2(M)"],
                        line=dict(width=2, color=color_map["R2(M)"]),
                    ),
                    hovertemplate="<b>%{x|%Y-%m-%d}</b><br>R2 %{y:.3f}<extra>R2 임계 초과</extra>",
                    showlegend=True,
                )
            )

        y_range = [0, max(line_df["value"])*1.1] if scale_mode=="0 기준 고정" else None
        fig_line.update_layout(
            height=420,
            margin=dict(l=10,r=10,t=10,b=10),
            legend=dict(title="지표", orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis=dict(title="Risk Level", range=y_range, gridcolor="rgba(0,0,0,0.05)"),
            xaxis=dict(title=None, showgrid=False),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )

        fig_line.add_hline(
            y=THRESH_R1, line=dict(color="#B10000", width=1, dash="dot"),
            annotation_text="R1 임계(0.149)", annotation_position="top left"
        )
        fig_line.add_hline(
            y=THRESH_R2, line=dict(color="#F5A623", width=1, dash="dot"),
            annotation_text="R2 임계(0.236)", annotation_position="top left"
        )

        st.plotly_chart(fig_line, use_container_width=True)

        st.markdown("##### 임계 초과 점검 알림")
        resolved_count = total_alert_count - remaining_alert_count
        if total_alert_count == 0:
            st.success("표시 기간 내 임계값 초과 이력이 없습니다.")
        else:
            summary = f"(총 {total_alert_count}회, 조치 {resolved_count}회)"
            if remaining_alert_count > 0:
                st.warning(f"현재 임계값 초과 {remaining_alert_count}회가 남아 있습니다. {summary}")
            else:
                st.success(f"현재 임계값 초과 항목은 없습니다. {summary}")

            if not alerts_table_display.empty:
                editor_cols = [
                    "번호", "점검완료", "점검일시", "초과지표",
                    "기준 위험레벨", "현재 위험레벨",
                    "기준 R_total", "현재 R_total",
                    "기준 R1(H/F/E)", "현재 R1(H/F/E)",
                    "기준 R2(M)", "현재 R2(M)",
                ]
                edited_alerts = st.data_editor(
                    alerts_table_display[editor_cols],
                    column_config={
                        "번호": st.column_config.NumberColumn("번호", format="%d", disabled=True),
                        "점검완료": st.column_config.CheckboxColumn("점검완료", help="점검 완료 시 체크"),
                        "점검일시": st.column_config.DateColumn("점검일시", disabled=True),
                        "초과지표": st.column_config.TextColumn("초과지표", disabled=True),
                        "기준 위험레벨": st.column_config.TextColumn("기준 위험레벨", disabled=True),
                        "현재 위험레벨": st.column_config.TextColumn("현재 위험레벨", disabled=True),
                        "기준 R_total": st.column_config.NumberColumn("기준 R_total", disabled=True, format="%.3f"),
                        "현재 R_total": st.column_config.NumberColumn("현재 R_total", disabled=True, format="%.3f"),
                        "기준 R1(H/F/E)": st.column_config.NumberColumn("기준 R1(H/F/E)", disabled=True, format="%.3f"),
                        "현재 R1(H/F/E)": st.column_config.NumberColumn("현재 R1(H/F/E)", disabled=True, format="%.3f"),
                        "기준 R2(M)": st.column_config.NumberColumn("기준 R2(M)", disabled=True, format="%.3f"),
                        "현재 R2(M)": st.column_config.NumberColumn("현재 R2(M)", disabled=True, format="%.3f"),
                    },
                    hide_index=True,
                    key="alerts_editor",
                )

                alerts_table_display = edited_alerts.copy()
                if not alerts_table_display.empty:
                    alerts_table_display["번호"] = alerts_table_display["번호"].astype(int)
                    alerts_table_display["점검완료"] = alerts_table_display["점검완료"].astype(bool)

                    new_checks = {}
                    for _, row in alerts_table_display.iterrows():
                        date_val = row["점검일시"]
                        if pd.isna(date_val):
                            continue
                        if isinstance(date_val, str):
                            date_obj = pd.to_datetime(date_val).date()
                        elif isinstance(date_val, pd.Timestamp):
                            date_obj = date_val.date()
                        elif isinstance(date_val, dt.date):
                            date_obj = date_val
                        else:
                            date_obj = pd.to_datetime(date_val).date()
                        new_checks[date_obj.isoformat()] = bool(row["점검완료"])
                    st.session_state["alert_checks"].update(new_checks)

    with tabs[2]:
        st.subheader("③ 공정 Gantt + 위험 오버레이")

        if sch.empty:
            st.info("공정 데이터가 없습니다.")
        else:
            st.markdown("##### 임계 초과 점검 일자")
            if alerts_table_display.empty:
                if total_alert_count == 0:
                    st.success("표시 기간 내 임계값 초과 일자가 없습니다.")
                else:
                    st.success("임계 초과 항목은 모두 점검 완료 상태입니다.")
            else:
                if remaining_alert_count > 0:
                    st.warning(f"임계 초과 일자 {remaining_alert_count}일 · 공정 영향 범위를 확인하세요.")
                else:
                    st.success("임계 초과 항목은 모두 점검 완료 상태입니다.")
                st.dataframe(
                    alerts_table_display,
                    use_container_width=True,
                    height=min(360, 80 + len(alerts_table_display) * 28),
                )

            g = sch.copy()
            g = g.dropna(subset=["planned_start","planned_end"])
            g["planned_start"] = pd.to_datetime(g["planned_start"])
            g["planned_end"]   = pd.to_datetime(g["planned_end"])

            fig_gantt = px.timeline(
                g,
                x_start="planned_start",
                x_end="planned_end",
                y="task_name",
                color="zone",
                hover_data=["task_id","hazard_codes"],
                title=None
            )
            red_days = view_daily.loc[view_daily["level"]=="Level I (Red)","date"].tolist()
            yellow_days = view_daily.loc[view_daily["level"]=="Level II (Yellow)","date"].tolist()
            for d in yellow_days:
                fig_gantt.add_vrect(
                    x0=pd.to_datetime(d),
                    x1=pd.to_datetime(d) + pd.Timedelta(days=1),
                    fillcolor="rgba(255,176,0,0.08)",
                    line_width=0,
                    layer="below"
                )
            for d in red_days:
                fig_gantt.add_vrect(
                    x0=pd.to_datetime(d),
                    x1=pd.to_datetime(d) + pd.Timedelta(days=1),
                    fillcolor="rgba(177,0,0,0.08)",
                    line_width=0,
                    layer="below"
                )

            today = pd.Timestamp(dt.date.today())
            fig_gantt.add_vline(x=today, line=dict(color="#1F6FEB", width=1, dash="dash"))

            fig_gantt.update_layout(
                height=520,
                margin=dict(l=10, r=10, t=10, b=10),
                legend_title_text="Zone",
                xaxis_title=None,
                yaxis_title=None,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_gantt, use_container_width=True)

    with tabs[3]:
        st.subheader("④ Top 위험요인/조합 바차트")

        # --- ④-1) 코드별 누적 가중치 막대 (TOP N, 가로 막대) ---
        # 코드별 누적 가중치(ΣRi0 = weight × count)
        code_counts = {}
        for codes in sch["hazard_codes"]:
            for c in codes:
                code_counts[c] = code_counts.get(c, 0) + 1

        code_rows = []
        for c, n in code_counts.items():
            w = CRITIC_WEIGHTS.get(c, 0.0)
            score = w * n
            code_rows.append({
                "code": str(c),                    # 축을 범주형으로 쓰기 위해 문자열 처리
                "name": HAZARD_NAMES.get(c, str(c)),
                "category": CODE_CAT.get(c, ""),   # H / F / E / M
                "count": n,
                "weight": w,
                "score": score
            })

        code_df = pd.DataFrame(code_rows).sort_values("score", ascending=False)

        # 상위 N개만 보기 (필요하면 N 숫자만 바꿔도 됨)
        TOP_N = 5
        top_df = code_df.head(TOP_N).copy()
        top_df["label"] = top_df.apply(
            lambda row: f"{row['name']} ({row['category']})" if row["name"] != row["code"] else f"{row['code']} ({row['category']})",
            axis=1
        )

        # --- ④-2) 막대 + 도넛을 나란히 배치 ---
        col1, col2 = st.columns([2, 1])

        with col1:
            fig_bar = px.bar(
                top_df,
                x="score",
                y="label",
                orientation="h",      # 가로 막대
                color="category",
                text="score",
                title=f"Top {TOP_N} 위험요인 (ΣRi0 기준)"
            )
            fig_bar.update_traces(
                texttemplate="%{text:.3f}",
                textposition="outside"
            )
            fig_bar.update_layout(
                xaxis_title="누적 기준위험도 (가중치 × 빈도)",
                yaxis_title="위험요인 이름 (카테고리)",
                yaxis=dict(categoryorder="total ascending"),  # 큰 값이 위로 오도록
                height=400,
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        with col2:
            # 일자별 위험 레벨 분포 도넛
            level_counts_raw = daily_df["level"].value_counts()
            level_order = ["Level I (Red)", "Level II (Yellow)", "Level III (Blue)"]
            total_days = int(level_counts_raw.sum())

            fig_levels = go.Figure()
            for lvl in level_order:
                days = int(level_counts_raw.get(lvl, 0))
                pct = (days / total_days * 100) if total_days else 0
                fig_levels.add_trace(
                    go.Bar(
                        x=[days],
                        y=["표시구간"],
                        name=f"{lvl}",
                        orientation="h",
                        marker=dict(color=level_color_map.get(lvl, "#CCCCCC")),
                        text=f"{pct:.0f}% ({days}일)" if days else "",
                        textposition="inside",
                        hovertemplate=f"{lvl}<br>일수: {days}일<br>비율: {pct:.1f}%<extra></extra>",
                    )
                )

            fig_levels.update_layout(
                title="레벨 분포 (표시구간)",
                barmode="stack",
                height=320,
                margin=dict(l=10, r=10, t=60, b=10),
                legend=dict(title="위험 레벨"),
                xaxis=dict(title="일수", showgrid=False, zeroline=False),
                yaxis=dict(title=None, showticklabels=False),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_levels, use_container_width=True)


    with tabs[4]:
        st.subheader("⑤ 기상 ↔ 위험도 상관")

        if view_daily.empty:
            st.info("표시구간 내 기상 데이터가 없습니다.")
        else:
            def interval_label(interval):
                if pd.isna(interval):
                    return "정보 없음"
                left = interval.left
                right = interval.right
                return f"{left:.1f}~{right:.1f}"

            def build_weather_heatmap(df, wind_bins=4, rain_bins=4):
                mask = df["wind_ms"].notna() & df["rain_mm"].notna()
                if mask.sum() < 2:
                    return None

                wind_series = df.loc[mask, "wind_ms"]
                rain_series = df.loc[mask, "rain_mm"]

                w_edges = np.linspace(wind_series.min(), wind_series.max(), wind_bins + 1)
                r_edges = np.linspace(rain_series.min(), rain_series.max(), rain_bins + 1)
                w_edges = np.unique(w_edges)
                r_edges = np.unique(r_edges)
                if len(w_edges) < 2 or len(r_edges) < 2:
                    return None

                wind_cut = pd.cut(wind_series, bins=w_edges, include_lowest=True, duplicates="drop")
                rain_cut = pd.cut(rain_series, bins=r_edges, include_lowest=True, duplicates="drop")

                temp = df.loc[mask].copy()
                temp["wind_bin"] = wind_cut.values
                temp["rain_bin"] = rain_cut.values

                agg = (
                    temp.groupby(["rain_bin", "wind_bin"])
                    .agg(avg_R=("R_total", "mean"), count=("R_total", "size"), red=("level", lambda x: (x == "Level I (Red)").sum()))
                    .reset_index()
                )
                if agg.empty:
                    return None

                agg["wind_label"] = agg["wind_bin"].apply(interval_label)
                agg["rain_label"] = agg["rain_bin"].apply(interval_label)
                agg["red_ratio"] = np.where(agg["count"] > 0, agg["red"] / agg["count"], 0.0)
                pivot_avg = agg.pivot(index="rain_label", columns="wind_label", values="avg_R")
                pivot_count = agg.pivot(index="rain_label", columns="wind_label", values="count").fillna(0).astype(int)
                pivot_red = agg.pivot(index="rain_label", columns="wind_label", values="red_ratio")

                rain_labels = list(pivot_avg.index)
                wind_labels = list(pivot_avg.columns)

                text_matrix = []
                for r in rain_labels:
                    row_text = []
                    for w in wind_labels:
                        val = pivot_avg.at[r, w] if (r in pivot_avg.index and w in pivot_avg.columns) else np.nan
                        cnt = pivot_count.at[r, w] if (r in pivot_count.index and w in pivot_count.columns) else 0
                        red_ratio = pivot_red.at[r, w] if (r in pivot_red.index and w in pivot_red.columns) else np.nan
                        if pd.isna(val):
                            row_text.append("")
                        else:
                            row_text.append(f"{val:.3f}<br>{cnt}일 · Level I {red_ratio*100:.0f}%")
                    text_matrix.append(row_text)

                fig = go.Figure(
                    data=go.Heatmap(
                        z=pivot_avg.values,
                        x=wind_labels,
                        y=rain_labels,
                        text=text_matrix,
                        texttemplate="%{text}",
                        colorscale=[
                            [0.0, "#E6F4EA"],
                            [0.5, "#F6E58D"],
                            [1.0, "#B10000"],
                        ],
                        colorbar=dict(title="평균 R_total"),
                        hoverinfo="text",
                    )
                )
                fig.update_layout(
                    title="풍속·강우량 조합별 평균 위험도",
                    xaxis=dict(title="풍속 구간(m/s)", showgrid=False),
                    yaxis=dict(title="강우량 구간(mm)", autorange="reversed", showgrid=False),
                    height=420,
                    margin=dict(l=10, r=20, t=50, b=10),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                return fig

            def build_weather_timeline(df):
                if df.empty:
                    return None
                plot_df = df.sort_values("date")
                timeline = make_subplots(specs=[[{"secondary_y": True}]])
                timeline.add_trace(
                    go.Scatter(
                        x=plot_df["date"],
                        y=plot_df["R_total"],
                        name="R_total",
                        line=dict(color="#B10000", width=3),
                        hovertemplate="날짜 %{x|%Y-%m-%d}<br>R_total %{y:.3f}<extra></extra>",
                    ),
                    secondary_y=False,
                )
                timeline.add_trace(
                    go.Bar(
                        x=plot_df["date"],
                        y=plot_df["rain_mm"],
                        name="일 강수량(mm)",
                        marker_color="rgba(80, 149, 255, 0.5)",
                        hovertemplate="날짜 %{x|%Y-%m-%d}<br>강수 %{y:.1f} mm<extra></extra>",
                    ),
                    secondary_y=True,
                )
                timeline.add_trace(
                    go.Scatter(
                        x=plot_df["date"],
                        y=plot_df["wind_ms"],
                        name="최대 풍속(m/s)",
                        mode="lines+markers",
                        line=dict(color="#1F6FEB", width=2, dash="dot"),
                        marker=dict(size=6),
                        hovertemplate="날짜 %{x|%Y-%m-%d}<br>풍속 %{y:.1f} m/s<extra></extra>",
                    ),
                    secondary_y=True,
                )
                timeline.update_yaxes(title_text="R_total", secondary_y=False)
                timeline.update_yaxes(title_text="강수·풍속", secondary_y=True)
                timeline.update_layout(
                    title="일자별 위험도 & 기상 추이",
                    height=420,
                    margin=dict(l=10, r=20, t=50, b=10),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    bargap=0.2,
                )
                return timeline

            heat_fig = build_weather_heatmap(view_daily)
            timeline_fig = build_weather_timeline(view_daily)

            col_heat, col_time = st.columns(2)

            with col_heat:
                if heat_fig is None:
                    st.info("풍속·강우량 조합으로 위험도를 계산할 수 있는 데이터가 충분하지 않습니다.")
                else:
                    st.plotly_chart(heat_fig, use_container_width=True)

            with col_time:
                if timeline_fig is None:
                    st.info("일자별 기상·위험 추세를 표시할 수 있는 데이터가 없습니다.")
                else:
                    st.plotly_chart(timeline_fig, use_container_width=True)

    with tabs[5]:
        st.subheader("데이터")
        t1, t2 = st.tabs(["Daily 결과", "Per-task 결과"])
        with t1:
            st.dataframe(view_daily, use_container_width=True, height=380)
            csv1 = view_daily.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ 표시구간 Daily CSV 다운로드", csv1, "daily_view.csv", "text/csv")
        with t2:
            st.dataframe(view_tasks, use_container_width=True, height=380)
            csv2 = view_tasks.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ 표시구간 Per-task CSV 다운로드", csv2, "per_task_view.csv", "text/csv")

    with tabs[6]:
        st.subheader("⑥ 붕괴위험 체크리스트")
        st.caption("현장 상황과 공정 특성에 맞춰 세부 점검 항목을 추가하거나 주기를 조정해 활용하세요.")

        for category in CHECKLIST_DATA:
            section_count = len(category["sections"])
            expander_label = f"{category['category']} · {section_count}개 세부항목"
            with st.expander(expander_label, expanded=False):
                for section in category["sections"]:
                    st.markdown(f"**{section['subcategory']}**")
                    items_df = pd.DataFrame(section["items"])
                    columns = ["점검항목", "설명", "점검주기", "담당자"]
                    if any(item.get("출처") for item in section["items"]):
                        columns.append("출처")
                    st.table(items_df[columns])
                    st.markdown("")

else:
    st.info("좌측에서 공정표 엑셀과 기상 엑셀을 업로드해주세요.")
