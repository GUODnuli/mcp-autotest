-- 取消指定任务的 SQL 脚本
-- 任务 ID: 7b3db333-6f68-4a08-b6a3-b93600e59363

-- 更新任务状态为 CANCELLED
UPDATE tasks 
SET 
    status = 'CANCELLED',
    updated_at = datetime('now'),
    error_message = '手动取消任务'
WHERE 
    task_id = '7b3db333-6f68-4a08-b6a3-b93600e59363';

-- 验证更新结果
SELECT 
    task_id,
    task_type,
    status,
    created_at,
    updated_at,
    error_message
FROM tasks 
WHERE task_id = '7b3db333-6f68-4a08-b6a3-b93600e59363';
