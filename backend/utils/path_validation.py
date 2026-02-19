#!/usr/bin/env python3
"""
AI PM Framework - Path Validation Utilities
Version: 1.0.0

パス生成時の安全性検証ユーティリティ。
絶対パスの混入やパストラバーサル攻撃を防ぐ。

Usage:
    from utils.path_validation import validate_path_components, safe_path_join

    # パスコンポーネントの検証
    validate_path_components("ORDER_123", "TASK_456")  # OK
    validate_path_components("/etc/passwd", "file.txt")  # ValueError

    # 安全なパス結合
    result_path = safe_path_join(base_dir, "RESULT", order_id, "04_TASKS")
"""

import os
import re
import sys
import warnings
from pathlib import Path
from typing import Union, List


class PathValidationError(ValueError):
    """パスバリデーションエラー"""
    pass


def validate_path_component(component: str, component_name: str = "path component") -> None:
    """
    パスコンポーネントが安全かを検証する

    以下の条件をチェック:
    - 絶対パスでないこと（os.path.isabs()がFalse）
    - 先頭が "/" または "\\" でないこと（Unix/Windows絶対パス）
    - ".." を含まないこと（パストラバーサル防止）
    - ドライブレター（Windows形式）を含まないこと

    Args:
        component: 検証対象のパスコンポーネント
        component_name: エラーメッセージ用のコンポーネント名

    Raises:
        PathValidationError: 検証に失敗した場合

    Examples:
        >>> validate_path_component("ORDER_123")  # OK
        >>> validate_path_component("/etc/passwd")  # raises PathValidationError
        >>> validate_path_component("../../../etc")  # raises PathValidationError
        >>> validate_path_component("C:\\Windows\\System32")  # raises PathValidationError
    """
    if not component:
        # 空文字列はスキップ（Noneの場合などに対応）
        return

    # 絶対パスチェック（OS固有の判定）
    if os.path.isabs(component):
        raise PathValidationError(
            f"{component_name} に絶対パスが指定されています: {component!r}"
        )

    # 先頭スラッシュチェック（Unix絶対パス、Windowsでもos.path.isabsがFalseになる場合がある）
    if component.startswith('/') or component.startswith('\\'):
        raise PathValidationError(
            f"{component_name} に絶対パス（先頭スラッシュ）が含まれています: {component!r}"
        )

    # パストラバーサルチェック（".." を含む）
    if ".." in component:
        raise PathValidationError(
            f"{component_name} にパストラバーサル（..）が含まれています: {component!r}"
        )

    # Windowsドライブレターチェック（"C:", "D:" など）
    # NOTE: order_idが "ORDER_123:456" のようなコロン付き文字列の可能性は低いが、
    # ドライブレター形式（1文字+コロン）に限定してチェック
    if len(component) >= 2 and component[1] == ":" and component[0].isalpha():
        raise PathValidationError(
            f"{component_name} にドライブレターが含まれています: {component!r}"
        )


def validate_path_components(*components: str) -> None:
    """
    複数のパスコンポーネントを一括検証

    Args:
        *components: 検証対象のパスコンポーネント（可変長引数）

    Raises:
        PathValidationError: いずれかの検証に失敗した場合

    Examples:
        >>> validate_path_components("ORDER_123", "04_TASKS", "TASK_456.md")  # OK
        >>> validate_path_components("ORDER_123", "/etc/passwd")  # raises PathValidationError
    """
    for idx, component in enumerate(components):
        if component is None:
            continue
        validate_path_component(str(component), f"component[{idx}]")


def safe_path_join(base: Union[str, Path], *components: str) -> Path:
    """
    安全なパス結合（絶対パス混入を防止）

    各コンポーネントが絶対パスでないことを検証してから結合する。
    os.path.join()やPathlib "/"演算子の代替として使用。

    Args:
        base: ベースパス（絶対パス可）
        *components: 結合するパスコンポーネント（相対パスのみ許可）

    Returns:
        Path: 結合されたパス

    Raises:
        PathValidationError: コンポーネントに絶対パスが含まれる場合

    Examples:
        >>> safe_path_join("/projects", "ai_pm_manager", "RESULT")
        PosixPath('/projects/ai_pm_manager/RESULT')

        >>> safe_path_join("/projects", "/etc/passwd")  # raises PathValidationError
    """
    # コンポーネント検証
    validate_path_components(*components)

    # パス結合
    result = Path(base)
    for component in components:
        if component:  # 空文字列はスキップ
            result = result / component

    return result


def normalize_task_id(task_id: str) -> str:
    """
    タスクIDを正規化（TASK_XXX形式に変換）

    Args:
        task_id: 元のタスクID（"123" または "TASK_123"）

    Returns:
        str: 正規化されたタスクID（"TASK_XXX"形式）

    Examples:
        >>> normalize_task_id("123")
        'TASK_123'
        >>> normalize_task_id("TASK_456")
        'TASK_456'
    """
    if not task_id.startswith("TASK_"):
        return f"TASK_{task_id}"
    return task_id


def sanitize_filename(filename: str, replace_char: str = "_") -> str:
    """
    ファイル名から危険な文字を除去/置換

    パスセパレータ（/, \）やコロン、制御文字などを置換する。

    Args:
        filename: 元のファイル名
        replace_char: 置換文字（デフォルト: "_"）

    Returns:
        str: サニタイズされたファイル名

    Examples:
        >>> sanitize_filename("task:123/report.md")
        'task_123_report.md'
        >>> sanitize_filename("ORDER_123")
        'ORDER_123'
    """
    # 危険な文字のリスト
    dangerous_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\x00']

    result = filename
    for char in dangerous_chars:
        result = result.replace(char, replace_char)

    return result


# ============================================================
# Roamingパス検証（BUG_011対策: Localへの書き込み防止）
# ============================================================

def is_local_path(path: Union[str, Path]) -> bool:
    """
    パスがAppData\\Local配下かどうかを判定

    Args:
        path: 検証対象のパス

    Returns:
        True if the path contains AppData\\Local
    """
    if sys.platform != "win32":
        return False
    path_str = str(path).lower().replace('/', '\\')
    return 'appdata\\local' in path_str


def is_roaming_path(path: Union[str, Path]) -> bool:
    """
    パスがAppData\\Roaming配下かどうかを判定

    Args:
        path: 検証対象のパス

    Returns:
        True if the path contains AppData\\Roaming
    """
    if sys.platform != "win32":
        return True  # 非Windowsではチェック不要
    path_str = str(path).lower().replace('/', '\\')
    return 'appdata\\roaming' in path_str


def convert_local_to_roaming(local_path: Union[str, Path]) -> str:
    """
    LocalパスをRoamingパスに変換

    AppData\\Local\\ai_pm_manager_v2 → AppData\\Roaming\\ai-pm-manager-v2

    Args:
        local_path: 変換対象のLocalパス

    Returns:
        Roamingパスに変換された文字列（変換不可の場合は元のパスを返す）
    """
    path_str = str(local_path)
    pattern = re.compile(
        r'(AppData)[/\\](Local)[/\\](ai_pm_manager_v2)',
        re.IGNORECASE
    )
    return pattern.sub(r'\1\\Roaming\\ai-pm-manager-v2', path_str)


def validate_roaming_path(
    file_path: Union[str, Path],
    auto_correct: bool = False
) -> Path:
    """
    ファイルパスがRoaming配下であることを検証する

    PROJECTS/配下の永続データがLocalに書き込まれることを防止する。
    Squirrelインストーラーの更新でLocalが上書きされるため必須。

    Args:
        file_path: 検証対象のパス
        auto_correct: Trueの場合、LocalパスをRoamingに自動変換

    Returns:
        検証済みのパス（auto_correct=Trueの場合は変換済み）

    Raises:
        PathValidationError: Localパスが検出され、auto_correct=Falseの場合
    """
    if sys.platform != "win32":
        return Path(file_path)

    path_str = str(file_path).lower()

    # PROJECTS/ を含むパスのみチェック
    if 'projects' not in path_str:
        return Path(file_path)

    if is_local_path(file_path):
        corrected = convert_local_to_roaming(str(file_path))
        if auto_correct:
            warnings.warn(
                f"Localパスを自動変換しました: {file_path} -> {corrected}",
                UserWarning,
                stacklevel=2
            )
            return Path(corrected)
        else:
            raise PathValidationError(
                f"PROJECTS配下のファイルがLocalパスで指定されています。"
                f"Roamingパスを使用してください。\n"
                f"  検出パス: {file_path}\n"
                f"  正しいパス: {corrected}\n"
                f"  ヒント: get_project_paths() でRoamingパスを取得してください"
            )
