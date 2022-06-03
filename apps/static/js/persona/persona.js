$(document).ready(function () {
  var $valor = $('#id_numero_documento');
  var $tipoBusqueda = $('#id_tipo_documento');
  var $btnLimpiar = $("#limpiar-dni");
  var $btnAsignarPersonal = $("#btn-asignar-personal");
  var $tipoPersonal = $("#id_tipo_personal");
  $("#id_profesion").select2({theme: 'bootstrap'});
  //$idPersona.select2({theme: 'bootstrap'});
  $btnLimpiar.click(function () {
    window.location = urlCrearPersonal
  });
  $tipoBusqueda.on('change', function () {
    var selectedOption = $(this).find('option:selected').val();
    verificarTipoDocumento(selectedOption);
  });
   verificarTipoDocumento($tipoBusqueda.val());
  $valor.keyup(function() {
    this.value = this.value.toUpperCase();
  });
  function verificarTipoDocumento(tipoDocumento) {
    if (tipoDocumento === '01'){ //dni
      $valor.inputmask({regex: "^([0-9]{1,8})$", placeholder:""});
    }
    else if (tipoDocumento === '03'){ //carnet extranjeria
      $valor.inputmask({regex: "^([0-9]{1,9})$", placeholder:""});
    }
    else if (tipoDocumento === '02'){//pasaporte
      $valor.inputmask({regex: "^([0-9A-Za-z]{1,12})$", placeholder:""});
    }
    else if (tipoDocumento === '04'){//cedula de identidad
      $valor.inputmask({regex: "^([0-9A-Za-z]{1,12})$", placeholder:""});
    }
    else if (tipoDocumento === '05'){//carnet de solicitante
      $valor.inputmask({regex: "^([0-9-]{5,11})$", placeholder:""});
    }
    else if (tipoDocumento === '00'){//sin documento
      $valor.inputmask({regex: "^([0-9A-Za-z-]{1,12})$", placeholder:""});
    }
  }

  var table_lista_persona = $("#lista-persona").DataTable({
    language: {
      "url":  datatablesES
    },
    ajax: urlListarPersona,
    searching: true,
    processing: true,
    serverSide: true,
    ordering: false,
  });

  if(tipPersona && (tipPersona === "consejo_facultad" || tipPersona === "consejo_unasam")){
    $(".f-ext").show();
    if(tipPersona === "consejo_unasam"){$("#div_id_facultad").hide();}else{$("#div_id_facultad").show();}
  }else{
    $(".f-ext").hide();
  }

  if($("#id_tipo_persona").val() && ($("#id_tipo_persona").val() === "consejo_facultad" || $("#id_tipo_persona").val() === "consejo_unasam")){
    $(".f-ext").show();
    if($("#id_tipo_persona").val() === "consejo_unasam"){$("#div_id_facultad").hide();}else{$("#div_id_facultad").show();}
  }else{
    $(".f-ext").hide();
  }

  $("#id_tipo_persona").on("change", function () {
   var selectedOption = $(this).find('option:selected').val();
    if(selectedOption && (selectedOption === "consejo_facultad" || selectedOption === "consejo_unasam")){
      $(".f-ext").show();
      if(selectedOption === "consejo_unasam"){$("#div_id_facultad").hide();}else{$("#div_id_facultad").show();}
    }else{
      $(".f-ext").hide();
    }
  });

  $("form").validate({
    rules: {
      'cargo_miembro': {
          "required": function(){
              return $("#id_tipo_persona").val() == "consejo_facultad" || $("#id_tipo_persona").val() == "consejo_unasam";
          }
      },
      'facultad': {
          "required": function(){
              return $("#id_tipo_persona").val() == "consejo_facultad";
          }
      }
    }
  });

  $("#lista-persona").on("click", ".eliminarc", function() {
    const id = $(this).attr("data-id");
    swal({
      title: "Importante",
      text: `¿Está seguro que desea eliminar a la persona seleccionada?`,
      type: "question",
      showCancelButton: true,
      confirmButtonColor: "#3085d6",
      cancelButtonColor: "#d33",
      confirmButtonText: "<i class='fa fa-check'></i> SI",
      cancelButtonText: "<i class='fa fa-times'></i> NO"
    }).then(function() {
      $.get(eliminarPersona.replace("id", id), function(data) {
        tipoMsg = data["tipo_msg"] ? 'warning': 'success';
        swal({
          text: data["msg"],
          type: tipoMsg
        }).then(function() {
          if (!data["tipo_msg"]){
            window.location.href = "/";
          }
        });
      }).fail(function(error) {
        swal({
          text: "Ocurrio un error al eliminar, intente nuevamente",
          type: "error"
        });
      });
    }).catch(() => {
      return;
    });
  });

  $(".selectmultiple").select2({width: '100%'});

  function llenaBrigada(select, brigadas, nro){
    $.getJSON(urlConsultaBrigada + "?id_punto_vacunacion="+select, function (res) {
      $(`#id_asignacionpersonal_set-${nro}-brigadas`).html(buildSelect(res.data));
      if (brigadas){
      $(`#id_asignacionpersonal_set-${nro}-brigadas`).val(brigadas);
    }
    });
  }

  $(".p-punto-vacunacion").on("change", function () {
   var regex = /(\d+)/g;
   var nro = $(this).attr('id').match(regex)
   var selectedOption = $(this).find('option:selected').val();
    if(selectedOption){
        llenaBrigada(selectedOption, '', nro);
    }
  });

  function buildSelect(data) {
    return data.map(function (elem) {
      return '<option value="' + elem.id + '">' + elem.nombre + '</option>';
    }).join('');
  }
  function llenaRol(select,id_rol,nro){
    $.getJSON(urlRolProfesional + "?tipo_personal="+select, function (res) {
      $(`#id_asignacionpersonal_set-${nro}-rol_profesional`).html(buildSelect(res.data));
      if(id_rol){
        $(`#id_asignacionpersonal_set-${nro}-rol_profesional`).val(id_rol)
      }
    });
  }
  $(".p-tipo-personal").on('change', function () {
    var regex = /(\d+)/g;
    var nro = $(this).attr('id').match(regex)
    var selectedOption = $(this).find('option:selected').val();
    if (selectedOption == EQUIPO_COORDINACION){
      $("#id_brigada").attr("disabled",true);
      $("#id_produccion").attr("disabled",true);
    }else{
      $("#id_brigada").attr("disabled",false);
      $("#id_produccion").attr("disabled",false);
    }
    llenaRol(selectedOption,'',nro)
  });

});
