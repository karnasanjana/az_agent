# Delete ONLY az_agent-created ADF objects. No containers/data touched.
# Run:  powershell -ExecutionPolicy Bypass -File .\delete_agent_adf.ps1
$RG = "Azure-data-lake"; $ADF = "azure-datalake-adf"
$script:ok = 0; $script:fail = 0
function Remove-AdfObj($sub, $name) {
  az datafactory $sub delete --name $name --factory-name $ADF --resource-group $RG --yes 2>$null
  if ($LASTEXITCODE -eq 0) { Write-Host "  deleted $sub $name"; $script:ok++ }
  else { Write-Host "  FAIL $sub $name"; $script:fail++ }
}
Write-Host "### triggers ###"
az datafactory trigger stop --name "s_tr_schedule_bike_store_analytics" --factory-name $ADF --resource-group $RG 2>$null
Remove-AdfObj "trigger" "s_tr_schedule_bike_store_analytics"
az datafactory trigger stop --name "tr_schedule_retail_r3" --factory-name $ADF --resource-group $RG 2>$null
Remove-AdfObj "trigger" "tr_schedule_retail_r3"
az datafactory trigger stop --name "tr_schedule_retail_executive_mart" --factory-name $ADF --resource-group $RG 2>$null
Remove-AdfObj "trigger" "tr_schedule_retail_executive_mart"
Write-Host "### pipelines (masters first) ###"
Remove-AdfObj "pipeline" "pl_master"
Remove-AdfObj "pipeline" "pl_orchestrator_pipeline"
Remove-AdfObj "pipeline" "pl_master_pipeline"
Remove-AdfObj "pipeline" "pl_master_covid_reporting"
Remove-AdfObj "pipeline" "pl_master_orchestrator"
Remove-AdfObj "pipeline" "pl_master_crm_analytics"
Remove-AdfObj "pipeline" "pl_master_sharepoint_ai"
Remove-AdfObj "pipeline" "pl_gold"
Remove-AdfObj "pipeline" "pl_silver"
Remove-AdfObj "pipeline" "pl_bronze"
Remove-AdfObj "pipeline" "pl_gold_layer_pipeline"
Remove-AdfObj "pipeline" "pl_silver_layer_pipeline"
Remove-AdfObj "pipeline" "pl_gold_pipeline"
Remove-AdfObj "pipeline" "pl_silver_pipeline"
Remove-AdfObj "pipeline" "pl_bronze_pipeline"
Remove-AdfObj "pipeline" "pl_bronze_covid"
Remove-AdfObj "pipeline" "pl_gold_covid"
Remove-AdfObj "pipeline" "pl_silver_covid"
Remove-AdfObj "pipeline" "pl_gold_layer"
Remove-AdfObj "pipeline" "pl_silver_layer"
Remove-AdfObj "pipeline" "pl_gold_reporting"
Remove-AdfObj "pipeline" "pl_silver_transforms"
Remove-AdfObj "pipeline" "pl_bronze_crm_analytics"
Remove-AdfObj "pipeline" "pl_gold_crm_analytics"
Remove-AdfObj "pipeline" "pl_silver_crm_analytics"
Remove-AdfObj "pipeline" "pl_gold_sharepoint_ai"
Remove-AdfObj "pipeline" "pl_silver_sharepoint_ai"
Write-Host "### data flows ###"
Remove-AdfObj "data-flow" "df_gold_category_performance"
Remove-AdfObj "data-flow" "df_gold_order_economics"
Remove-AdfObj "data-flow" "df_silver_order_items"
Remove-AdfObj "data-flow" "df_silver_orders"
Remove-AdfObj "data-flow" "df_silver_products"
Remove-AdfObj "data-flow" "df_gold_breaches_by_country"
Remove-AdfObj "data-flow" "df_gold_breaches_by_priority"
Remove-AdfObj "data-flow" "df_silver_account"
Remove-AdfObj "data-flow" "df_silver_incident"
Remove-AdfObj "data-flow" "df_gold_completion_state"
Remove-AdfObj "data-flow" "df_gold_completion_state_output"
Remove-AdfObj "data-flow" "df_gold_owner_workload"
Remove-AdfObj "data-flow" "df_gold_owner_workload_output"
Remove-AdfObj "data-flow" "df_silver_dol_project_team"
Remove-AdfObj "data-flow" "df_gold_basket_detail"
Remove-AdfObj "data-flow" "df_gold_customer_category_spend"
Remove-AdfObj "data-flow" "df_silver_customers"
Remove-AdfObj "data-flow" "df_gold_task_load_by_staff"
Remove-AdfObj "data-flow" "df_gold_work_mix_by_business_unit"
Remove-AdfObj "data-flow" "df_silver_staff"
Remove-AdfObj "data-flow" "df_silver_tasks"
Remove-AdfObj "data-flow" "df_gold_daily_revenue"
Remove-AdfObj "data-flow" "df_gold_revenue_by_city"
Remove-AdfObj "data-flow" "df_gold_revenue_by_segment"
Remove-AdfObj "data-flow" "df_silver_contact"
Remove-AdfObj "data-flow" "df_gold_country_fatality"
Remove-AdfObj "data-flow" "df_gold_united_nations"
Remove-AdfObj "data-flow" "df_silver_countries_aggregated"
Remove-AdfObj "data-flow" "df_gold_category_economics"
Remove-AdfObj "data-flow" "df_gold_seasonal_orders"
Remove-AdfObj "data-flow" "df_gold_top_customers_in_target_cities"
Remove-AdfObj "data-flow" "df_gold_value_band_mix"
Remove-AdfObj "data-flow" "df_gold_sales_by_category"
Remove-AdfObj "data-flow" "df_gold_sales_by_city"
Remove-AdfObj "data-flow" "df_gold_top_customers"
Remove-AdfObj "data-flow" "df_gold_country_totals"
Remove-AdfObj "data-flow" "df_gold_united_nations_active_cases"
Remove-AdfObj "data-flow" "df_gold_orders_by_status"
Remove-AdfObj "data-flow" "df_gold_revenue_by_category"
Remove-AdfObj "data-flow" "df_gold_revenue_by_customer"
Remove-AdfObj "data-flow" "df_gold_cases_by_origin"
Remove-AdfObj "data-flow" "df_gold_cases_by_priority"
Remove-AdfObj "data-flow" "df_gold_contacts_by_city"
Remove-AdfObj "data-flow" "df_gold_contacts_by_organization"
Remove-AdfObj "data-flow" "df_silver_accounts"
Remove-AdfObj "data-flow" "df_silver_contacts"
Remove-AdfObj "data-flow" "df_silver_incidents"
Remove-AdfObj "data-flow" "df_gold_opportunities_by_industry"
Remove-AdfObj "data-flow" "df_gold_opportunities_by_status"
Remove-AdfObj "data-flow" "df_silver_ai_clients"
Remove-AdfObj "data-flow" "df_silver_ai_opportunities"
Write-Host "### datasets ###"
Remove-AdfObj "dataset" "ds_bronze_order_items"
Remove-AdfObj "dataset" "ds_bronze_orders"
Remove-AdfObj "dataset" "ds_bronze_products"
Remove-AdfObj "dataset" "ds_bronze_account"
Remove-AdfObj "dataset" "ds_bronze_incident"
Remove-AdfObj "dataset" "ds_dataverse_account"
Remove-AdfObj "dataset" "ds_dataverse_incident"
Remove-AdfObj "dataset" "ds_bronze_dol_project_team"
Remove-AdfObj "dataset" "ds_bronze_customers"
Remove-AdfObj "dataset" "ds_bronze_staff"
Remove-AdfObj "dataset" "ds_bronze_tasks"
Remove-AdfObj "dataset" "ds_dataverse_staff"
Remove-AdfObj "dataset" "ds_bronze_contact"
Remove-AdfObj "dataset" "ds_dataverse_contact"
Remove-AdfObj "dataset" "ds_bronze_countries_aggregated"
Remove-AdfObj "dataset" "ds_landing_countries_aggregated"
Remove-AdfObj "dataset" "ds_bronze_accounts"
Remove-AdfObj "dataset" "ds_bronze_contacts"
Remove-AdfObj "dataset" "ds_bronze_incidents"
Remove-AdfObj "dataset" "ds_dataverse_accounts"
Remove-AdfObj "dataset" "ds_dataverse_contacts"
Remove-AdfObj "dataset" "ds_dataverse_incidents"
Remove-AdfObj "dataset" "ds_bronze_ai_clients"
Remove-AdfObj "dataset" "ds_bronze_ai_opportunities"
Write-Host "### linked services ###"
Remove-AdfObj "linked-service" "ls_storage"
Remove-AdfObj "linked-service" "ls_dataverse_zcscmdemodev_crm_dynamics_com"
Remove-AdfObj "linked-service" "ls_http_raw_githubusercontent_com"
Write-Host "DONE  deleted=$($script:ok)  failed=$($script:fail)"
