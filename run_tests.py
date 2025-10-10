#!/usr/bin/env python3
"""
Скрипт для запуска тестов с различными опциями
"""
import subprocess
import sys
import os
import argparse


def run_command(command):
    """Выполняет команду и возвращает результат"""
    print(f"Выполняем: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)
    
    if result.stdout:
        print("STDOUT:", result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description='Запуск тестов pytest с Allure')
    parser.add_argument('--markers', '-m', help='Запустить тесты с определенными маркерами')
    parser.add_argument('--parallel', '-n', type=int, help='Количество параллельных процессов')
    parser.add_argument('--coverage', '-c', action='store_true', help='Включить покрытие кода')
    parser.add_argument('--html', action='store_true', help='Создать HTML отчет')
    parser.add_argument('--allure-report', action='store_true', help='Создать Allure отчет')
    parser.add_argument('--verbose', '-v', action='store_true', help='Подробный вывод')
    parser.add_argument('--file', '-f', help='Запустить тесты из конкретного файла')
    
    args = parser.parse_args()
    
    # Базовые команды pytest
    cmd = ['python', '-m', 'pytest']
    
    # Добавляем опции
    if args.verbose:
        cmd.append('-v')
    
    if args.markers:
        cmd.extend(['-m', args.markers])
    
    if args.parallel:
        cmd.extend(['-n', str(args.parallel)])
    
    if args.coverage:
        cmd.extend(['--cov=.', '--cov-report=html', '--cov-report=term'])
    
    if args.html:
        cmd.extend(['--html=report.html', '--self-contained-html'])
    
    if args.file:
        cmd.append(args.file)
    else:
        cmd.append('tests/')
    
    # Запускаем тесты
    success = run_command(cmd)
    
    # Создаем Allure отчет если нужно
    if args.allure_report and success:
        print("\nСоздаем Allure отчет...")
        allure_cmd = ['allure', 'generate', 'allure-results', '-o', 'allure-report', '--clean']
        run_command(allure_cmd)
        
        print("\nОткрываем Allure отчет...")
        open_cmd = ['allure', 'open', 'allure-report']
        run_command(open_cmd)
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
